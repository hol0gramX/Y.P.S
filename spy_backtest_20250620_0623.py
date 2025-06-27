import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= 配置 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========= 数据获取 =========
def fetch_data(start_date, end_date):
    df = yf.download(SYMBOL, start=start_date, end=end_date, interval="1m", progress=False)
    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    df.index.name = "Datetime"
    if not df.index.tz:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df.ta.rsi(length=14, append=True)
    df['RSI'] = df['RSI_14']
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df['MACD'] = df['MACD_12_26_9']
    df['MACDh'] = df['MACDh_12_26_9']
    df['MACDs'] = df['MACDs_12_26_9']
    df.ffill(inplace=True)
    return df.dropna()

# ========= 判断函数 =========
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
    return (row['Close'] > row['VWAP'] and row['RSI'] > 53 and
            row['MACD'] > 0 and row['MACDh'] > 0 and
            row['RSI_SLOPE'] > 0.15 and strong_volume(row))

def check_put_entry(row):
    return (row['Close'] < row['VWAP'] and row['RSI'] < 47 and
            row['MACD'] < 0 and row['MACDh'] < 0 and
            row['RSI_SLOPE'] < -0.15 and strong_volume(row))

def check_call_exit(row):
    return (row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and
            (row['MACD'] < 0.05 or row['MACDh'] < 0.05))

def check_put_exit(row):
    return (row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and
            (row['MACD'] > -0.05 or row['MACDh'] > -0.05))

def allow_call_reentry(row, prev):
    return (prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and
            row['RSI'] > 53 and row['MACDh'] > 0.1 and strong_volume(row))

def allow_put_reentry(row, prev):
    return (prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and
            row['RSI'] < 47 and row['MACDh'] < 0.05 and strong_volume(row))

# ========= 回测主逻辑 =========
def backtest(start_date, end_date):
    print(f"[🔁 回测开始] {start_date} 到 {end_date}")
    df = fetch_data(start_date, end_date)
    position = "none"
    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

        if position == "call" and check_call_exit(row):
            strength = determine_strength(row, "call")
            position = "none"
            if check_put_entry(row):
                strength_put = determine_strength(row, "put")
                position = "put"
                signals.append(f"[{ts}] 🔁 反手 Put：Call 结构破坏 + Put 入场（{strength_put}）")
            else:
                signals.append(f"[{ts}] ⚠️ Call 出场信号（{strength}）")

        elif position == "put" and check_put_exit(row):
            strength = determine_strength(row, "put")
            position = "none"
            if check_call_entry(row):
                strength_call = determine_strength(row, "call")
                position = "call"
                signals.append(f"[{ts}] 🔁 反手 Call：Put 结构破坏 + Call 入场（{strength_call}）")
            else:
                signals.append(f"[{ts}] ⚠️ Put 出场信号（{strength}）")

        elif position == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                position = "call"
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}）")
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                position = "put"
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}）")
            elif allow_call_reentry(row, prev):
                strength = determine_strength(row, "call")
                position = "call"
                signals.append(f"[{ts}] 📈 趋势回补 Call 再入场（{strength}）")
            elif allow_put_reentry(row, prev):
                strength = determine_strength(row, "put")
                position = "put"
                signals.append(f"[{ts}] 📉 趋势回补 Put 再入场（{strength}）")

    for sig in signals:
        print(sig)

# ========= 执行入口 =========
if __name__ == "__main__":
    start = datetime(2025, 6, 20, tzinfo=EST)
    end = datetime(2025, 6, 24, tzinfo=EST)
    backtest(start, end)
