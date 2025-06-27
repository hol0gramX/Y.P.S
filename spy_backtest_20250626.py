import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置区域 =========
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 数据获取 =========
def fetch_data():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df = df.tz_localize("UTC").tz_convert(EST)
    df = df[df.index.time >= time(9, 30)]

    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACDs"] = macd["MACDs_12_26_9"]
        df["MACDh"] = macd["MACDh_12_26_9"]
    else:
        df["MACD"] = df["MACDs"] = df["MACDh"] = float("nan")

    df["RSI_slope"] = df["RSI"].diff()
    df["RSI_slope2"] = df["RSI_slope"].diff()

    return df.dropna()

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    position = None
    entry_time = None

    for i in range(2, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        rsi = row["RSI"]
        macdh = row["MACDh"]
        slope = row["RSI_slope"]
        slope2 = row["RSI_slope2"]

        time_str = row.name.strftime("%Y-%m-%d %H:%M:%S")

        # Call 入场条件
        if (rsi > 53 and macdh > 0 and slope > 0 and slope2 > 0 and position != "call"):
            signals.append(f"[{time_str}] 📈 主升浪 Call 入场（趋势：未知）")
            position = "call"
            entry_time = row.name

        # Put 入场条件
        elif (rsi < 47 and macdh < 0 and slope < 0 and slope2 < 0 and position != "put"):
            signals.append(f"[{time_str}] 📉 主跌浪 Put 入场（趋势：未知）")
            position = "put"
            entry_time = row.name

        # 出场逻辑（5分钟后）
        elif position and (row.name - entry_time).total_seconds() >= 300:
            signals.append(f"[{time_str}] ⚠️ {position.capitalize()} 出场信号（趋势：未知）")
            position = None
            entry_time = None

    return signals

# ========= 回测主程序 =========
def backtest():
    df = fetch_data()
    signals = generate_signals(df)
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")

    with open("signal_log_backtest.csv", "w") as f:
        for line in signals:
            f.write(line + "\n")
            print(line)

if __name__ == "__main__":
    backtest()

