import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)

def is_market_day(dt):
    sched = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not sched.empty

def get_ema_trend(df, idx, window=5):
    if idx < window:
        return "unknown"
    ema_series = df['EMA20'].iloc[idx-window+1:idx+1]
    increasing = all(x < y for x, y in zip(ema_series, ema_series[1:]))
    decreasing = all(x > y for x, y in zip(ema_series, ema_series[1:]))
    if increasing:
        return "up"
    elif decreasing:
        return "down"
    else:
        return "sideways"

def is_sideways(row, df, idx, window=3, price_threshold=0.002, ema_threshold=0.02):
    price_near = abs(row['Close'] - row['EMA20']) / row['EMA20'] < price_threshold
    if idx < window:
        return False
    ema_now = row['EMA20']
    ema_past = df.iloc[idx - window]['EMA20']
    ema_flat = abs(ema_now - ema_past) < ema_threshold
    return price_near and ema_flat

def is_top_chop(df, idx, window=4):
    if idx < window:
        return False
    recent = df.iloc[idx - window + 1:idx + 1]
    return (recent['MACDh'].max() - recent['MACDh'].min() < 0.01) and (recent['RSI'].mean() > 60)

def fetch_data(start_date, end_date):
    df = yf.download(
        SYMBOL,
        start=start_date,
        end=end_date + timedelta(days=1),
        interval="1m",
        prepost=True,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        raise ValueError("无数据")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df = df[~df.index.duplicated(keep='last')]

    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    df['EMA20'] = ta.ema(df['Close'], length=20)

    df.dropna(subset=['High', 'Low', 'Close', 'RSI', 'RSI_SLOPE', 'MACD', 'MACDh', 'EMA20'], inplace=True)

    return df

def determine_strength(row, direction):
    ema_diff_ratio = (row['Close'] - row['EMA20']) / row['EMA20']
    rsi_slope = row.get('RSI_SLOPE', 0)

    if direction == "call":
        if row['RSI'] >= 60 and row['MACDh'] > 0.3 and ema_diff_ratio > 0.002:
            return "强"
        elif row['RSI'] >= 55 and row['MACDh'] > 0 and ema_diff_ratio > 0:
            return "中"
        elif row['RSI'] < 50 or ema_diff_ratio < 0:
            return "弱"
        else:
            return "中" if rsi_slope > 0.1 else "弱"

    elif direction == "put":
        if row['RSI'] <= 40 and row['MACDh'] < -0.3 and ema_diff_ratio < -0.002:
            return "强"
        elif row['RSI'] <= 45 and row['MACDh'] < 0 and ema_diff_ratio < 0:
            return "中"
        elif row['RSI'] > 50 or ema_diff_ratio > 0:
            return "弱"
        else:
            return "中" if rsi_slope < -0.1 else "弱"

    return "中"

def check_call_entry(row, trend):
    return (
        trend == "up" and
        row['Close'] > row['EMA20'] and
        row['RSI'] > 53 and
        row['MACD'] > 0 and
        row['MACDh'] > 0.01 and
        row['RSI_SLOPE'] > 0.15
    )

def check_put_entry(row, trend):
    return (
        trend == "down" and
        row['Close'] < row['EMA20'] and
        row['RSI'] < 47 and
        row['MACD'] < 0 and
        row['MACDh'] < -0.01 and
        row['RSI_SLOPE'] < -0.15
    )

def allow_bottom_rebound_call(row, prev):
    return (
        row['Close'] < row['EMA20'] and
        row['RSI'] > prev['RSI'] and
        row['MACDh'] > prev['MACDh'] and
        row['MACD'] > -0.3
    )

def allow_top_rebound_put(row, prev):
    return (
        row['Close'] > row['EMA20'] and
        row['RSI'] < prev['RSI'] and
        row['MACDh'] < prev['MACDh'] and
        row['MACD'] < 0.3
    )

def check_call_exit(row):
    return (
        row['RSI'] < 50 and
        row['RSI_SLOPE'] < 0 and
        (row['MACD'] < 0.05 or row['MACDh'] < 0.05)
    )

def check_put_exit(row):
    return (
        row['RSI'] > 50 and
        row['RSI_SLOPE'] > 0 and
        (row['MACD'] > -0.05 or row['MACDh'] > -0.05)
    )

def is_trend_continuation(row, prev, position):
    if position == "call":
        return (row['MACDh'] > 0) and (row['RSI'] > 45)
    elif position == "put":
        return (row['MACDh'] < 0) and (row['RSI'] < 55)
    return False

def backtest(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    print(f"[🔁 回测时间区间] {start_date} ~ {end_date}")

    df = fetch_data(start_date, end_date)
    print(f"数据条数：{len(df)}")

    position = "none"
    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name
        ttime = ts.time()

        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            if ttime >= time(15, 59) and position != "none":
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")
                position = "none"
            continue

        ema_trend = get_ema_trend(df, i)

        # 持仓时判断出场信号
        if position == "call":
            if check_call_exit(row):
                if is_trend_continuation(row, prev, position):
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏳ 趋势中继豁免，Call 持仓不出场")
                else:
                    strength = determine_strength(row, "call")
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Call 出场信号（{strength}）")
                    position = "none"
            continue

        if position == "put":
            if check_put_exit(row):
                if is_trend_continuation(row, prev, position):
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏳ 趋势中继豁免，Put 持仓不出场")
                else:
                    strength = determine_strength(row, "put")
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Put 出场信号（{strength}）")
                    position = "none"
            continue

        # 无持仓时先过滤震荡（横盘+顶部震荡）
        if position == "none":
            if is_sideways(row, df, i) or is_top_chop(df, i):
                # print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 震荡区间，跳过入场")
                continue

            if check_call_entry(row, ema_trend):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📈 Call 入场（{strength}）")
                position = "call"
            elif check_put_entry(row, ema_trend):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📉 Put 入场（{strength}）")
                position = "put"
            elif allow_bottom_rebound_call(row, prev):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📈 底部反弹 Call 捕捉（{strength}）")
                position = "call"
            elif allow_top_rebound_put(row, prev):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📉 顶部反转 Put 捕捉（{strength}）")
                position = "put"

    last_ts = df.index[-1]
    if last_ts.time() < REGULAR_END and position != "none":
        signals.append(f"[{last_ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")

    print(f"总信号数：{len(signals)}")
    for s in signals:
        print(s)

if __name__ == "__main__":
    backtest("2025-06-20", "2025-06-27")

