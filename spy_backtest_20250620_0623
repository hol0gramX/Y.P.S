# spy_backtest_20250620_0623.py

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
def fetch_data(start, end):
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", progress=False)
    if df.empty:
        return pd.DataFrame()

    df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    if not df.index.tz:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]

    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df = df.dropna()

    return df

# ========= RSI 斜率 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i-5:i+1]).iloc[-1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        # === Call 入场 ===
        if in_position != "CALL":
            if rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}，趋势：增强）")
                in_position = "CALL"

        # === Call 出场 ===
        elif in_position == "CALL":
            if rsi < 50 and slope < 0 and macd < 0:
                signals.append(f"[{ts}] ⚠️ Call 出场信号（趋势：转弱）")
                in_position = None

        # === Put 入场 ===
        if in_position != "PUT":
            if rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}，趋势：增强）")
                in_position = "PUT"

        # === Put 出场 ===
        elif in_position == "PUT":
            if rsi > 50 and slope > 0 and macd > 0:
                signals.append(f"[{ts}] ⚠️ Put 出场信号（趋势：转弱）")
                in_position = None

    return signals

# ========= 回测入口 =========
def backtest_for_day(day_str):
    start = datetime.strptime(day_str, "%Y-%m-%d")
    end = start + timedelta(days=1)
    print(f"\n[🔁 回测开始] {day_str}")

    df = fetch_data(start, end)
    if df.empty:
        print(f"[⚠️] {day_str} 没有交易数据（可能为休市日）")
        return

    signals = generate_signals(df)
    if not signals:
        print("[ℹ️] 无信号触发")
    else:
        for sig in signals:
            print(sig)

if __name__ == "__main__":
    backtest_for_day("2025-06-20")
    backtest_for_day("2025-06-23")
