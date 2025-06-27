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

# ========= 反转辅助判断 =========
def allow_bottom_rebound_call(row, prev_row):
    return (
        prev_row["Close"] < prev_row["BBL_20_2.0"] and
        row["Close"] > row["BBL_20_2.0"] and
        row["RSI"] < 35 and
        row["MACDh"] > -0.2 and
        row["MACD"] > prev_row["MACD"]
    )

def allow_top_rebound_put(row, prev_row):
    return (
        prev_row["Close"] > prev_row["BBU_20_2.0"] and
        row["Close"] < row["BBU_20_2.0"] and
        row["RSI"] > 65 and
        row["MACDh"] < 0.2 and
        row["MACD"] < prev_row["MACD"]
    )

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        # === Call 主升浪入场 ===
        if in_position != "CALL":
            if row["RSI"] > 53 and slope > 0.15 and row["MACD"] > 0 and row["MACDh"] > 0:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}，趋势：增强）")
                in_position = "CALL"
                continue

        # === Call 出场 ===
        if in_position == "CALL":
            if row["RSI"] < 50 and slope < 0 and row["MACD"] < 0:
                signals.append(f"[{ts}] ⚠️ Call 出场信号（趋势：转弱）")
                in_position = None
                continue

        # === Put 主跌浪入场 ===
        if in_position != "PUT":
            if row["RSI"] < 47 and slope < -0.15 and row["MACD"] < 0 and row["MACDh"] < 0:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}，趋势：增强）")
                in_position = "PUT"
                continue

        # === Put 出场 ===
        if in_position == "PUT":
            if row["RSI"] > 50 and slope > 0 and row["MACD"] > 0:
                signals.append(f"[{ts}] ⚠️ Put 出场信号（趋势：转弱）")
                in_position = None
                continue

        # === 布林带底部反弹 Call ===
        if in_position is None and allow_bottom_rebound_call(row, prev):
            signals.append(f"[{ts}] 🌀 谷底布林带反弹 Call 入场（RSI={row['RSI']:.1f}）")
            in_position = "CALL"
            continue

        # === 布林带顶部回落 Put ===
        if in_position is None and allow_top_rebound_put(row, prev):
            signals.append(f"[{ts}] 🔻 高位布林带反压 Put 入场（RSI={row['RSI']:.1f}）")
            in_position = "PUT"
            continue

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
