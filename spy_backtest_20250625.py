import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def compute_indicators(df):
    df['RSI_6'] = ta.rsi(df['Close'], length=6).fillna(50)
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    df['MACDh_slope'] = df['MACDh'].diff().fillna(0)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14).fillna(method='bfill')
    df['Bar_Size'] = (df['High'] - df['Low']).fillna(0)
    df['Bar_Body'] = (df['Close'] - df['Open']).abs().fillna(0)
    df['Body_MA5'] = df['Bar_Body'].rolling(5).mean().fillna(0.01)
    df['Vol_MA5'] = df['Volume'].rolling(5).mean().fillna(1)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['Prev_High'] = df['High'].shift(1).fillna(method='bfill')
    df['Prev_Low'] = df['Low'].shift(1).fillna(method='bfill')
    return df.dropna()

def strong_volume(row): return row['Volume'] >= row['Vol_MA5']
def trending_up(row): return row['MACD'] > row['MACDs'] and row['MACDh'] > 0 and row['MACDh_slope'] > 0
def trending_down(row): return row['MACD'] < row['MACDs'] and row['MACDh'] < 0 and row['MACDh_slope'] < 0
def valid_candle(row): return row['Bar_Body'] > row['Body_MA5'] * 0.8
def not_choppy(row): return row['ATR'] > 0.15

def check_call_entry(row):
    return (
        row['Close'] > row['VWAP'] and
        row['RSI_6'] > 52 and
        strong_volume(row) and
        trending_up(row) and
        valid_candle(row) and
        row['Close'] > row['Prev_High'] and
        not_choppy(row)
    )

def check_put_entry(row):
    return (
        row['Close'] < row['VWAP'] and
        row['RSI_6'] < 48 and
        strong_volume(row) and
        trending_down(row) and
        valid_candle(row) and
        row['Close'] < row['Prev_Low'] and
        not_choppy(row)
    )

def check_call_exit(row): return row['RSI_6'] < 48 and strong_volume(row)
def check_put_exit(row): return row['RSI_6'] > 52 and strong_volume(row)

def determine_strength(row, direction):
    strength = "中"
    if direction == "call":
        if row['RSI_6'] > 65 and row['MACDh'] > 0.5:
            strength = "强"
        elif row['RSI_6'] < 55:
            strength = "弱"
    elif direction == "put":
        if row['RSI_6'] < 35 and row['MACDh'] < -0.5:
            strength = "强"
        elif row['RSI_6'] > 45:
            strength = "弱"
    return strength

def run_backtest():
    df = yf.download(SYMBOL, interval="1m", start="2025-06-24", end="2025-06-26", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = compute_indicators(df)

    state = {"position": "none"}
    results = []

    for idx, row in df.iterrows():
        current_pos = state["position"]
        est_time = idx.tz_localize("UTC").astimezone(EST) if idx.tzinfo is None else idx.astimezone(EST)

        if current_pos == "call" and check_call_exit(row):
            results.append((est_time, "⚠️ Call 出场信号"))
            state["position"] = "none"
            if check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                results.append((est_time, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"))

        elif current_pos == "put" and check_put_exit(row):
            results.append((est_time, "⚠️ Put 出场信号"))
            state["position"] = "none"
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                results.append((est_time, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"))

        elif current_pos == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                results.append((est_time, f"📈 主升浪 Call 入场（{strength}）"))
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                results.append((est_time, f"📉 主跌浪 Put 入场（{strength}）"))

    return results

if __name__ == "__main__":
    for t, signal in run_backtest():
        print(f"[{t.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}")
