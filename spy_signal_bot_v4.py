import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

STATE_FILE = "last_signal.json"
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

def get_est_now():
    return datetime.now(tz=ZoneInfo("America/New_York"))

def get_data():
    now = get_est_now()
    start = now - timedelta(minutes=30)
    req = StockBarsRequest(
        symbol_or_symbols=SYMBOL,
        timeframe=TimeFrame.Minute,
        start=start
    )
    bars = client.get_stock_bars(req).df
    df = bars[bars.index.get_level_values(0) == SYMBOL].copy()
    df.index = df.index.droplevel(0)
    df = df.sort_index()

    df['Vol_MA5'] = df['volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['close'], 14)
    df['VWAP'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
    return df.dropna()

def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(window=length).mean()
    avg_loss = down.rolling(window=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def strong_volume(row):
    return row['volume'] >= row['Vol_MA5']

def check_call_entry(row):
    return (
        row['close'] > row['vwap'] and
        row['RSI'] > 52 and
        strong_volume(row)
    )

def check_put_entry(row):
    return (
        row['close'] < row['vwap'] and
        row['RSI'] < 48 and
        strong_volume(row)
    )

def check_call_exit(row):
    return (row['RSI'] < 48) and strong_volume(row)

def check_put_exit(row):
    return (row['RSI'] > 52) and strong_volume(row)

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
    time_index = row.name
    state = load_last_signal()
    current_pos = state.get("position", "none")

    if current_pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            state["position"] = "put"
            save_last_signal(state)
            return time_index, "🔁 反手 Put：Call 结构破坏 + Put 入场条件成立"
        return time_index, "⚠️ Call 出场信号"

    elif current_pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            state["position"] = "call"
            save_last_signal(state)
            return time_index, "🔁 反手 Call：Put 结构破坏 + Call 入场条件成立"
        return time_index, "⚠️ Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row):
            state["position"] = "call"
            save_last_signal(state)
            return time_index, "📈 主升浪 Call 入场"
        elif check_put_entry(row):
            state["position"] = "put"
            save_last_signal(state)
            return time_index, "📉 主跌浪 Put 入场"

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

