# 完整回测版本：完全复刻主策略行为（包含 VWAP, RSI斜率, 再入场, Volume判断, 5min趋势, 仓位状态）

import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 技术指标计算 =========
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df

def get_5min_trend():
    df_5min = yf.download(SYMBOL, interval='5m', period='2d', progress=False)
    df_5min = compute_macd(df_5min)
    last = df_5min.iloc[-1]
    if last['MACDh'] > 0.1:
        return "up"
    elif last['MACDh'] < -0.1:
        return "down"
    else:
        return "neutral"

# ========= 数据准备 =========
def fetch_data(start_date, end_date):
    df = yf.download(SYMBOL, interval="1m", start=start_date, end=end_date, progress=False, prepost=True, auto_adjust=True)
    df.index = df.index.tz_localize("UTC").tz_convert(EST)
    df = df.dropna(subset=['High','Low','Close','Volume'])
    df = df[df['Volume'] > 0]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# ========= 信号判断逻辑 =========
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']

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
    return (row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and strong_volume(row))

def check_put_entry(row):
    return (row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and strong_volume(row))

def check_call_exit(row):
    return (row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05))

def check_put_exit(row):
    return (row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05))

def allow_call_reentry(row, prev):
    return (prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACDh'] > 0.1 and strong_volume(row))

def allow_put_reentry(row, prev):
    return (prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACDh'] < -0.05 and strong_volume(row))

# ========= 回测逻辑 =========
def backtest(start_date, end_date):
    print(f"[🔁 回测开始] {start_date.date()} 到 {end_date.date()}")
    df = fetch_data(start_date, end_date)
    trend_5min = get_5min_trend()

    signals = []
    position = "none"

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

        if position == "call" and check_call_exit(row):
            strength = determine_strength(row, "call")
            position = "none"
            if check_put_entry(row):
                strength2 = determine_strength(row, "put")
                signals.append(f"[{ts}] 🔁 反手 Put：Call 结构破坏 + Put 入场（{strength2}，5min趋势：{trend_5min}）")
                position = "put"
            else:
                signals.append(f"[{ts}] ⚠️ Call 出场信号（{strength}，5min趋势：{trend_5min}）")

        elif position == "put" and check_put_exit(row):
            strength = determine_strength(row, "put")
            position = "none"
            if check_call_entry(row):
                strength2 = determine_strength(row, "call")
                signals.append(f"[{ts}] 🔁 反手 Call：Put 结构破坏 + Call 入场（{strength2}，5min趋势：{trend_5min}）")
                position = "call"
            else:
                signals.append(f"[{ts}] ⚠️ Put 出场信号（{strength}，5min趋势：{trend_5min}）")

        elif position == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}，5min趋势：{trend_5min}）")
                position = "call"
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}，5min趋势：{trend_5min}）")
                position = "put"
            elif allow_call_reentry(row, prev_row):
                strength = determine_strength(row, "call")
                signals.append(f"[{ts}] 📈 趋势回补 Call 再入场（{strength}，5min趋势：{trend_5min}）")
                position = "call"
            elif allow_put_reentry(row, prev_row):
                strength = determine_strength(row, "put")
                signals.append(f"[{ts}] 📉 趋势回补 Put 再入场（{strength}，5min趋势：{trend_5min}）")
                position = "put"

    for sig in signals:
        print(sig)

if __name__ == "__main__":
    start = datetime(2025, 6, 20, 4, 0, tzinfo=EST)
    end = datetime(2025, 6, 24, 4, 0, tzinfo=EST)
    backtest(start, end)
