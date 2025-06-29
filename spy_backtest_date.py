import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========== 配置 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)

# ========== 时间工具 ==========
def is_market_day(dt):
    sched = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not sched.empty

# ========== 数据获取 ==========
def fetch_data(start_date, end_date):
    # 包含end_date当天全天数据，end+1日才截止
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

    # 时区转换
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 去重
    df = df[~df.index.duplicated(keep='last')]

    # 计算指标
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    # 丢弃必要字段空值
    df.dropna(subset=['High', 'Low', 'Close', 'Volume', 'Vol_MA5', 'RSI', 'RSI_SLOPE', 'VWAP', 'MACD', 'MACDh'], inplace=True)

    return df

# ========== 信号逻辑 ==========
def strong_volume(row):
    return row['Volume'] >= row['Vol_MA5']

def determine_strength(row, direction):
    vwap_diff_ratio = (row['Close'] - row['VWAP']) / row['VWAP']
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5 and vwap_diff_ratio > 0.005:
            return "强"
        elif row['RSI'] < 55 or vwap_diff_ratio < 0:
            return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5 and vwap_diff_ratio < -0.005:
            return "强"
        elif row['RSI'] > 45 or vwap_diff_ratio > 0:
            return "弱"
    return "中"

def check_call_entry(row):
    return (
        row['Close'] > row['VWAP'] and
        row['RSI'] > 53 and
        row['MACD'] > 0 and
        row['MACDh'] > 0 and
        row['RSI_SLOPE'] > 0.15
    )

def check_put_entry(row):
    return (
        row['Close'] < row['VWAP'] and
        row['RSI'] < 47 and
        row['MACD'] < 0 and
        row['MACDh'] < 0 and
        row['RSI_SLOPE'] < -0.15
    )

def allow_bottom_rebound_call(row, prev):
    return (
        row['Close'] < row['VWAP'] and
        row['RSI'] > prev['RSI'] and
        row['MACDh'] > prev['MACDh'] and
        row['MACD'] > -0.3
    )

def allow_top_rebound_put(row, prev):
    return (
        row['Close'] > row['VWAP'] and
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

def allow_call_reentry(row, prev):
    return (
        prev['Close'] < prev['VWAP'] and
        row['Close'] > row['VWAP'] and
        row['RSI'] > 53 and
        row['MACDh'] > 0.1
    )

def allow_put_reentry(row, prev):
    return (
        prev['Close'] > prev['VWAP'] and
        row['Close'] < row['VWAP'] and
        row['RSI'] < 47 and
        row['MACDh'] < 0.05
    )

# ========== 回测主逻辑 ==========
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

        # 只在常规交易时间内操作
        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            # 收盘强制清仓
            if ttime >= time(15, 59) and position != "none":
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")
                position = "none"
            continue

        if position == "call":
            if check_call_exit(row):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Call 出场信号（{strength}）")
                position = "none"
                # 反手Put判定
                if check_put_entry(row) or allow_top_rebound_put(row, prev):
                    strength_put = determine_strength(row, "put")
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 🔁 反手 Put 入场（{strength_put}）")
                    position = "put"
            continue

        if position == "put":
            if check_put_exit(row):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Put 出场信号（{strength}）")
                position = "none"
                # 反手Call判定
                if check_call_entry(row) or allow_bottom_rebound_call(row, prev):
                    strength_call = determine_strength(row, "call")
                    signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 🔁 反手 Call 入场（{strength_call}）")
                    position = "call"
            continue

        if position == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📈 Call 入场（{strength}）")
                position = "call"
            elif check_put_entry(row):
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
            elif allow_call_reentry(row, prev):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📈 趋势回补 Call 再入场（{strength}）")
                position = "call"
            elif allow_put_reentry(row, prev):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] 📉 趋势回补 Put 再入场（{strength}）")
                position = "put"

    # 收盘强制清仓最后确认（防止最后一分钟没触发）
    last_ts = df.index[-1]
    last_time = last_ts.time()
    if last_time < REGULAR_END and position != "none":
        signals.append(f"[{last_ts.strftime('%Y-%m-%d %H:%M:%S')}] ⏰ 收盘前自动清仓，状态复位")
        position = "none"

    print(f"总信号数：{len(signals)}")
    for s in signals:
        print(s)


if __name__ == "__main__":
    # 示例，传入回测日期
    backtest("2025-06-26", "2025-06-27")





