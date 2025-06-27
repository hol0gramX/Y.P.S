import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= 配置 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========= 数据函数 =========
def fetch_data():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
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

# ========= 斜率函数 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

# ========= 信号函数 =========
def generate_signals(df):
    signals = []
    in_position = None
    last_signal_time = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i-5:i+1]).iloc[-1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

        if in_position != "CALL":
            if rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（趋势：增强）")
                in_position = "CALL"
                last_signal_time = ts
        elif in_position == "CALL":
            if rsi < 50 or slope < 0:
                signals.append(f"[{ts}] ⚠️ Call 出场信号（趋势：转弱）")
                in_position = None

        if in_position != "PUT":
            if rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（趋势：增强）")
                in_position = "PUT"
                last_signal_time = ts
        elif in_position == "PUT":
            if rsi > 50 or slope > 0:
                signals.append(f"[{ts}] ⚠️ Put 出场信号（趋势：转弱）")
                in_position = None

    return signals

# ========= 回测函数 =========
def backtest():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()
