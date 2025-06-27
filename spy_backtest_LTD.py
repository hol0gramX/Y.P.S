# 完整升级后的回测脚本：逻辑与主策略保持一致
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
PREMARKET_START = time(4, 0)
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 数据获取 =========
def fetch_data():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True, auto_adjust=True)
    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    df.index.name = "Datetime"
    if not df.index.tz:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]

    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    bbands = df.ta.bbands(length=20, std=2.0)
    df = pd.concat([df, macd, bbands], axis=1)

    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df["VWAP"] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = df.dropna()
    return df

# ========= 工具函数 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

def is_market_day(ts):
    cal = nasdaq.schedule(start_date=ts.date(), end_date=ts.date())
    return not cal.empty

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

def allow_bollinger_rebound(row, prev_row, direction):
    if direction == "CALL":
        return (
            prev_row["Close"] < prev_row["BBL_20_2.0"] and
            row["Close"] > row["BBL_20_2.0"] and
            row["RSI"] > 48 and row["MACD"] > 0
        )
    elif direction == "PUT":
        return (
            prev_row["Close"] > prev_row["BBU_20_2.0"] and
            row["Close"] < row["BBU_20_2.0"] and
            row["RSI"] < 52 and row["MACD"] < 0
        )
    return False

def allow_bottom_rebound_call(row, prev):
    return (row['Close'] < row['VWAP'] and row['RSI'] > prev['RSI'] and row['MACDh'] > prev['MACDh'] and row['MACD'] > -0.3)

def allow_top_rebound_put(row, prev):
    return (row['Close'] > row['VWAP'] and row['RSI'] < prev['RSI'] and row['MACDh'] < prev['MACDh'] and row['MACD'] < 0.3)

def allow_call_reentry(row, prev):
    return (prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACDh'] > 0.1)

def allow_put_reentry(row, prev):
    return (prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACDh'] < 0.05)

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")
        current_time = row.name.time()

        if not is_market_day(row.name):
            continue

        if current_time < PREMARKET_START:
            continue

        if current_time < REGULAR_START and df.iloc[i - 1].name.date() != row.name.date():
            in_position = None

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]

        strength_call = determine_strength(row, "call")
        strength_put = determine_strength(row, "put")

        if in_position == "CALL" and rsi < 50 and slope < 0 and macd < 0:
            signals.append(f"[{ts}] ⚠️ Call 出场信号（{strength_call}）")
            in_position = None
            if (rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0) or allow_top_rebound_put(row, prev_row):
                signals.append(f"[{ts}] 📉 反手 Put：Call 结构破坏 + Put 入场（{strength_put}）")
                in_position = "PUT"
            continue

        if in_position == "PUT" and rsi > 50 and slope > 0 and macd > 0:
            signals.append(f"[{ts}] ⚠️ Put 出场信号（{strength_put}）")
            in_position = None
            if (rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0) or allow_bottom_rebound_call(row, prev_row):
                signals.append(f"[{ts}] 📈 反手 Call：Put 结构破坏 + Call 入场（{strength_call}）")
                in_position = "CALL"
            continue

        if in_position != "CALL":
            allow_call = (
                (rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0) or
                allow_bollinger_rebound(row, prev_row, "CALL") or
                allow_bottom_rebound_call(row, prev_row) or
                allow_call_reentry(row, prev_row)
            )
            if allow_call:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength_call}）")
                in_position = "CALL"
                continue

        if in_position != "PUT":
            allow_put = (
                (rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0) or
                allow_bollinger_rebound(row, prev_row, "PUT") or
                allow_top_rebound_put(row, prev_row) or
                allow_put_reentry(row, prev_row)
            )
            if allow_put:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength_put}）")
                in_position = "PUT"
                continue

    return signals

# ========= 回测入口 =========
def backtest():
    print(f"[🔁 回溯开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()

