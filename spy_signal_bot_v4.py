import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta

STATE_FILE = "last_signal.json"
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def get_est_now():
    return datetime.now(tz=ZoneInfo("America/New_York"))

def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(window=length).mean()
    avg_loss = down.rolling(window=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(df):
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9']
    df['MACDs'] = macd['MACDs_12_26_9']
    df['MACDh'] = macd['MACDh_12_26_9']
    return df

def get_data():
    df = yf.download(SYMBOL, interval="1m", period="1d", progress=False)
    df = df.dropna()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    return df.dropna()

def get_data_5min():
    df = yf.download(SYMBOL, interval="5m", period="1d", progress=False)
    df = df.dropna()
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    return df

def strong_volume(row):
    return row['Volume'] >= row['Vol_MA5']

def macd_trending_up(row):
    return row['MACD'] > row['MACDs'] and row['MACDh'] > 0

def macd_trending_down(row):
    return row['MACD'] < row['MACDs'] and row['MACDh'] < 0

def confirm_5min_trend():
    df5 = get_data_5min()
    if len(df5) < 2:
        return "未知"
    last = df5.iloc[-1]
    if last['EMA5'] > last['EMA20']:
        return "多头"
    elif last['EMA5'] < last['EMA20']:
        return "空头"
    return "震荡"

def determine_strength(row, direction):
    strength = "中"
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5:
            strength = "强"
        elif row['RSI'] < 55:
            strength = "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5:
            strength = "强"
        elif row['RSI'] > 45:
            strength = "弱"
    return strength

def check_call_entry(row):
    return (
        row['Close'] > row['VWAP'] and
        row['RSI'] > 52 and
        strong_volume(row) and
        macd_trending_up(row)
    )

def check_put_entry(row):
    return (
        row['Close'] < row['VWAP'] and
        row['RSI'] < 48 and
        strong_volume(row) and
        macd_trending_down(row)
    )

def check_call_exit(row):
    return row['RSI'] < 48 and strong_volume(row)

def check_put_exit(row):
    return row['RSI'] > 52 and strong_volume(row)

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
    time_index = row.name
    state = load_last_signal()
    current_pos = state.get("position", "none")

    if current_pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index, f"反手 Put：Call 结构破坏 + Put 入场（{strength}）"
        return time_index, "Call 出场信号"

    elif current_pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index, f"反手 Call：Put 结构破坏 + Call 入场（{strength}）"
        return time_index, "Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index, f"主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index, f"主跌浪 Put 入场（{strength}）"
    return None, None

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
    df = get_data()
    time_signal, signal = generate_signal(df)
    if signal:
        msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S')}] {signal}"
        print(msg)
        send_to_discord(msg)
    else:
        print(f"[{get_est_now().strftime('%Y-%m-%d %H:%M:%S')}] 无信号")

if __name__ == "__main__":
    main()


