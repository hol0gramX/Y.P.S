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
def fetch_data():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df.columns = df.columns.get_level_values(0)
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
    df = df.dropna()
    return df

# ========= RSI 斜率 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

# ========= 布林带反弹判断 =========
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

# ========= 信号生成 =========
def determine_strength(rsi, slope, macdh):
    if rsi > 65 and macdh > 0.5 and slope > 0.25:
        return "强"
    elif rsi < 55 or slope < 0.1:
        return "弱"
    return "中"

def generate_signals(df):
    signals = []
    in_position = None
    last_date = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        ts = row.name
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")

        # 每天开盘自动空仓归零
        if last_date != ts.date():
            in_position = None
            last_date = ts.date()

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i-5:i+1]).iloc[-1]
        strength = determine_strength(rsi, slope, macdh)

        if in_position != "CALL":
            allow_call = (
                (rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0) or
                allow_bollinger_rebound(row, prev_row, "CALL")
            )
            if allow_call:
                signals.append(f"[{ts_str}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                continue

        if in_position == "CALL":
            if rsi < 50 and slope < 0 and macd < 0:
                signals.append(f"[{ts_str}] ⚠️ Call 出场信号（{strength}）")
                in_position = None

        if in_position != "PUT":
            allow_put = (
                (rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0) or
                allow_bollinger_rebound(row, prev_row, "PUT")
            )
            if allow_put:
                signals.append(f"[{ts_str}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                continue

        if in_position == "PUT":
            if rsi > 50 and slope > 0 and macd > 0:
                signals.append(f"[{ts_str}] ⚠️ Put 出场信号（{strength}）")
                in_position = None

    return signals

# ========= 回测入口 =========
def backtest():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()
