import os
import json
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta

STATE_FILE = "last_signal.json"
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def get_est_now():
    return datetime.now(tz=ZoneInfo("America/New_York"))

def compute_indicators(df):
    df['RSI_6'] = ta.rsi(df['Close'], length=6).fillna(50)
    df['MACD'] = ta.macd(df['Close'])['MACD_12_26_9'].fillna(0)
    df['MACDs'] = ta.macd(df['Close'])['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = ta.macd(df['Close'])['MACDh_12_26_9'].fillna(0)
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

def strong_volume(row):
    return float(row['Volume']) >= float(row['Vol_MA5'])

def trending_up(row):
    return row['MACD'] > row['MACDs'] and row['MACDh'] > 0 and row['MACDh_slope'] > 0

def trending_down(row):
    return row['MACD'] < row['MACDs'] and row['MACDh'] < 0 and row['MACDh_slope'] < 0

def valid_candle(row):
    return row['Bar_Body'] > row['Body_MA5'] * 0.8

def not_choppy(row):
    return row['ATR'] > 0.15

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

def check_call_exit(row):
    return row['RSI_6'] < 48 and strong_volume(row)

def check_put_exit(row):
    return row['RSI_6'] > 52 and strong_volume(row)

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

def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def generate_signal(df):
    if len(df) < 6:
        return None, None
    row = df.iloc[-1]
    state = load_last_signal()
    current_pos = state.get("position", "none")

    time_index = row.name
    if time_index.tzinfo is None:
        time_index = time_index.tz_localize("UTC")
    time_index_est = time_index.tz_convert(ZoneInfo("America/New_York"))

    if current_pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"
        return time_index_est, "⚠️ Call 出场信号"

    elif current_pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"
        return time_index_est, "⚠️ Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"📈 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"📉 主跌浪 Put 入场（{strength}）"

    return None, None

def get_data():
    df = yf.download(SYMBOL, interval="1m", period="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = compute_indicators(df)
    return df

def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未设置")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("发送 Discord 失败：", e)

def main():
    try:
        df = get_data()
        time_signal, signal = generate_signal(df)
        if signal and time_signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{get_est_now().strftime('%Y-%m-%d %H:%M:%S %Z')}] 无信号")
    except Exception as e:
        print("运行出错：", e)

if __name__ == "__main__":
    main()
