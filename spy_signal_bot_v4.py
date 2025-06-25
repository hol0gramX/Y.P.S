import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo
import requests
import json

STATE_FILE = "last_signal.json"
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

def get_est_now():
    return datetime.now(tz=ZoneInfo('America/New_York'))

def in_trading_hours():
    now = get_est_now().time()
    return time(9,30) <= now <= time(16,0)

def get_data():
    df = yf.download("SPY", interval="1m", period="1d", progress=False, auto_adjust=True)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])

    df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
    df['EMA5'] = ta.ema(df['Close'], length=5)
    df['EMA10'] = ta.ema(df['Close'], length=10)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['MA50'] = ta.sma(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    df['PrevLow'] = df['Low'].rolling(window=5).min().shift(1)
    df['PrevHigh'] = df['High'].rolling(window=5).max().shift(1)

    return df.dropna()

def strong_volume(row):
    return row['Volume'] >= 1.05 * row['Vol_MA5']

def check_call_entry(row, prev):
    return (
        (row['Close'] > row['VWAP']) and
        (row['EMA5'] > row['EMA10'] > row['EMA20']) and
        (row['Close'] > row['MA50']) and
        (row['MACD_12_26_9'] > row['MACDs_12_26_9']) and
        (row['MACD_12_26_9'] > prev['MACD_12_26_9']) and
        (row['MACDh_12_26_9'] > 0) and
        (row['RSI'] > 50) and
        strong_volume(row)
    )

def check_put_entry(row, prev):
    return (
        (row['Close'] < row['VWAP']) and
        (row['EMA5'] < row['EMA10'] < row['EMA20']) and
        (row['Close'] < row['MA50']) and
        (row['MACD_12_26_9'] < row['MACDs_12_26_9']) and
        (row['MACDh_12_26_9'] < prev['MACDh_12_26_9']) and
        (row['MACDh_12_26_9'] < 0) and
        (row['RSI'] < 50) and
        strong_volume(row)
    )

def check_call_exit(row, prev):
    return (
        (row['Close'] < row['EMA10']) or
        (row['MACDh_12_26_9'] < prev['MACDh_12_26_9']) or
        (row['RSI'] < 48)
    ) and strong_volume(row)

def check_put_exit(row, prev):
    return (
        (row['Close'] > row['EMA10']) or
        (row['MACDh_12_26_9'] > prev['MACDh_12_26_9']) or
        (row['RSI'] > 52)
    ) and strong_volume(row)

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
    prev = df.iloc[-2]
    time_index = df.index[-1]

    state = load_last_signal()
    current_pos = state.get("position", "none")

    if current_pos == "call" and check_call_exit(row, prev):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row, prev):
            state["position"] = "put"
            save_last_signal(state)
            return time_index, "🔁 反手 Put：Call 结构破坏 + Put 入场条件成立"
        return time_index, "⚠️ Call 出场信号"

    elif current_pos == "put" and check_put_exit(row, prev):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row, prev):
            state["position"] = "call"
            save_last_signal(state)
            return time_index, "🔁 反手 Call：Put 结构破坏 + Call 入场条件成立"
        return time_index, "⚠️ Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row, prev):
            state["position"] = "call"
            save_last_signal(state)
            return time_index, "📈 主升浪 Call 入场"
        elif check_put_entry(row, prev):
            state["position"] = "put"
            save_last_signal(state)
            return time_index, "📉 主跌浪 Put 入场"

    return None, None

def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未设置，跳过发送")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("发送 Discord 失败：", e)

def main():
    now = get_est_now()
    if not in_trading_hours():
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 非交易时间，不拉数据也不发信号")
        return

    df = get_data()
    time_signal, signal = generate_signal(df)
    if signal:
        msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S')}] {signal}"
        print(msg)
        send_to_discord(msg)
    else:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 无信号")

if __name__ == "__main__":
    main()
