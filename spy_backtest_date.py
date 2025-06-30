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
    delta = ema_series.iloc[-1] - ema_series.iloc[0]
    if abs(delta) < 0.01:
        return "sideways"
    if all(x < y for x, y in zip(ema_series, ema_series[1:])):
        return "up"
    if all(x > y for x, y in zip(ema_series, ema_series[1:])):
        return "down"
    return "sideways"

def is_sideways(row, df, idx, window=3):
    if idx < window:
        return False
    recent = df.iloc[idx-window+1:idx+1]
    rsi_range = recent['RSI'].max() - recent['RSI'].min()
    macdh_range = recent['MACDh'].max() - recent['MACDh'].min()
    price_near_ema = abs(row['Close'] - row['EMA20']) / row['EMA20'] < 0.001
    return (rsi_range < 10) and (macdh_range < 0.02) and price_near_ema

def is_top_chop(df, idx, window=4):
    if idx < window:
        return False
    recent = df.iloc[idx - window + 1:idx + 1]
    return (recent['MACDh'].max() - recent['MACDh'].min() < 0.01) and (recent['RSI'].mean() > 60)

def fetch_data(start_date, end_date):
    df = yf.download(SYMBOL, start=start_date, end=end_date + timedelta(days=1), interval="1m", prepost=True, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError("无数据")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
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
        if row['RSI'] >= 60 and row['MACDh'] >= 0.03 and ema_diff_ratio >= 0.001:
            return "强"
        elif row['RSI'] >= 55 and row['MACDh'] > 0 and ema_diff_ratio > 0:
            return "中"
        return "弱"

    if direction == "put":
        if row['RSI'] <= 40 and row['MACDh'] <= -0.03 and ema_diff_ratio <= -0.001:
            return "强"
        elif row['RSI'] <= 45 and row['MACDh'] < 0 and ema_diff_ratio < 0:
            return "中"
        return "弱"

    return "中"

def check_call_entry(row, trend):
    if trend != "up": return False
    if (abs(row['MACDh']) < 0.02 and 45 <= row['RSI'] <= 55): return False
    return row['RSI'] >= 60 and row['MACDh'] >= 0.03 and (row['Close'] - row['EMA20']) / row['EMA20'] >= 0.001

def check_put_entry(row, trend):
    if trend != "down": return False
    if (abs(row['MACDh']) < 0.02 and 45 <= row['RSI'] <= 55): return False
    return row['RSI'] <= 40 and row['MACDh'] <= -0.03 and (row['Close'] - row['EMA20']) / row['EMA20'] <= -0.001

def allow_bottom_rebound_call(row, prev):
    return row['Close'] < row['EMA20'] and row['RSI'] > prev['RSI'] and row['MACDh'] > prev['MACDh'] and row['MACD'] > -0.3

def allow_top_rebound_put(row, prev):
    return row['Close'] > row['EMA20'] and row['RSI'] < prev['RSI'] and row['MACDh'] < prev['MACDh'] and row['MACD'] < 0.3

def check_call_exit(row):
    return row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05)

def check_put_exit(row):
    return row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05)

def is_trend_continuation(row, prev, position):
    if position == "call": return row['MACDh'] > 0 and row['RSI'] > 45
    if position == "put": return row['MACDh'] < 0 and row['RSI'] < 55
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
        row, prev = df.iloc[i], df.iloc[i - 1]
        ts, ttime = row.name, row.name.time()

        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            if ttime >= time(15, 59) and position != "none":
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")
                position = "none"
            continue

        ema_trend = get_ema_trend(df, i)

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

        if position == "none":
            if is_sideways(row, df, i) or is_top_chop(df, i): continue
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

    if df.index[-1].time() < REGULAR_END and position != "none":
        signals.append(f"[{df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")

    print(f"总信号数：{len(signals)}")
    for s in signals:
        print(s)

if __name__ == "__main__":
    backtest("2025-06-20", "2025-06-27")
