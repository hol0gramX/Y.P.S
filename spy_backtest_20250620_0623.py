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
    df = yf.download(SYMBOL, start=start_date, end=end_date + timedelta(days=1), interval="1m", progress=False)
    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]
    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    bbands = df.ta.bbands(length=20)
    df = pd.concat([df, macd, bbands], axis=1)
    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df["BBU"] = df["BBU_20_2.0"]
    df["BBL"] = df["BBL_20_2.0"]
    df = df.dropna()
    return df

# ========= RSI 斜率 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

# ========= 反弹判断 =========
def allow_bottom_rebound_call(row, prev):
    return (
        row['Close'] < row['BBL'] and
        row['RSI'] > prev['RSI'] and
        row['MACDh'] > prev['MACDh'] and
        row['MACD'] > -0.3 and
        row['Volume'] > prev['Volume'].rolling(5).mean()
    )

def allow_top_rebound_put(row, prev):
    return (
        row['Close'] > row['BBU'] and
        row['RSI'] < prev['RSI'] and
        row['MACDh'] < prev['MACDh'] and
        row['MACD'] < 0.3 and
        row['Volume'] > prev['Volume'].rolling(5).mean()
    )

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    last_signal_time = None
    last_signal_type = None
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")
        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        exited = False

        if in_position == "CALL" and rsi < 50 and slope < 0 and macd < 0:
            signals.append(f"[{ts}] ⚠️ Call 出场信号（趋势：转弱）")
            in_position = None
            exited = True

        elif in_position == "PUT" and rsi > 50 and slope > 0 and macd > 0:
            signals.append(f"[{ts}] ⚠️ Put 出场信号（趋势：转弱）")
            in_position = None
            exited = True

        if in_position is None and (last_signal_time is None or row.name != last_signal_time):
            if rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_type = "CALL"
                last_signal_time = row.name

            elif rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_type = "PUT"
                last_signal_time = row.name

            elif allow_bottom_rebound_call(row, prev):
                signals.append(f"[{ts}] 📉 底部反弹 Call 捕捉（评分：4/5）")
                in_position = "CALL"
                last_signal_type = "CALL"
                last_signal_time = row.name

            elif allow_top_rebound_put(row, prev):
                signals.append(f"[{ts}] 📈 顶部反转 Put 捕捉（评分：3/5）")
                in_position = "PUT"
                last_signal_type = "PUT"
                last_signal_time = row.name

    return signals

# ========= 回测入口 =========
def backtest(start_date, end_date):
    print(f"[🔁 回测开始] {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    df = fetch_data(start_date, end_date)
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    start = datetime(2025, 6, 20, tzinfo=EST)
    end = datetime(2025, 6, 24, tzinfo=EST)
    backtest(start, end)
