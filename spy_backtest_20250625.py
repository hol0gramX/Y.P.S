import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import timedelta

# 参数设置
symbol = "SPY"
min_hold = 5  # 最小持仓分钟数

def compute_indicators(df):
    df['RSI'] = ta.rsi(df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    return df.dropna()

def is_strong_volume(row):
    return row['Volume'] >= row['Vol_MA5']

def macd_trending(df, i, direction):
    recent = df.iloc[i-3:i]
    if direction == "up":
        return (recent['MACD_12_26_9'] > recent['MACDs_12_26_9']).all() and (recent['MACDh_12_26_9'] > 0).all()
    elif direction == "down":
        return (recent['MACD_12_26_9'] < recent['MACDs_12_26_9']).all() and (recent['MACDh_12_26_9'] < 0).all()
    return False

def determine_strength(row, direction):
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh_12_26_9'] > 0.5:
            return "强"
        elif row['RSI'] < 55:
            return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh_12_26_9'] < -0.5:
            return "强"
        elif row['RSI'] > 45:
            return "弱"
    return "中"

def backtest(df):
    position = "none"
    entry_time = None
    logs = []

    for i in range(5, len(df)):
        row = df.iloc[i]
        now = row.name

        can_exit = entry_time is not None and (now - entry_time) >= timedelta(minutes=min_hold)

        if position == "call":
            exit_signal = row['RSI'] < 48 and is_strong_volume(row) and not macd_trending(df, i, "up") and can_exit
            if exit_signal:
                logs.append(f"[{now}] ⚠️ Call 出场信号")
                position = "none"
                entry_time = None
                # check反手 Put
                if (
                    row['Close'] < row['VWAP'] and row['RSI'] < 50 and is_strong_volume(row)
                    and macd_trending(df, i, "down")
                ):
                    strength = determine_strength(row, "put")
                    logs.append(f"[{now}] 🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）")
                    position = "put"
                    entry_time = now
                continue

        elif position == "put":
            exit_signal = row['RSI'] > 52 and is_strong_volume(row) and not macd_trending(df, i, "down") and can_exit
            if exit_signal:
                logs.append(f"[{now}] ⚠️ Put 出场信号")
                position = "none"
                entry_time = None
                # check反手 Call
                if (
                    row['Close'] > row['VWAP'] and row['RSI'] > 50 and is_strong_volume(row)
                    and macd_trending(df, i, "up")
                ):
                    strength = determine_strength(row, "call")
                    logs.append(f"[{now}] 🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）")
                    position = "call"
                    entry_time = now
                continue

        if position == "none":
            if (
                row['Close'] > row['VWAP'] and row['RSI'] > 50 and is_strong_volume(row)
                and macd_trending(df, i, "up")
            ):
                strength = determine_strength(row, "call")
                logs.append(f"[{now}] 📈 主升浪 Call 入场（{strength}）")
                position = "call"
                entry_time = now
            elif (
                row['Close'] < row['VWAP'] and row['RSI'] < 50 and is_strong_volume(row)
                and macd_trending(df, i, "down")
            ):
                strength = determine_strength(row, "put")
                logs.append(f"[{now}] 📉 主跌浪 Put 入场（{strength}）")
                position = "put"
                entry_time = now

    return logs

if __name__ == "__main__":
    df = yf.download("SPY", interval="1m", start="2025-06-25", end="2025-06-26", progress=False, auto_adjust=False)
    df = compute_indicators(df)
    signals = backtest(df)
    for s in signals:
        print(s)

