import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import requests
import json

STATE_FILE = "last_signal.json"
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

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
        (row['MACDh_12_26_9'] < prev['MACDh_12_26_9']) and  # 放宽至只需动能下行
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
    time = df.index[-1]

    state = load_last_signal()
    current_pos = state.get("position", "none")

    if current_pos == "call" and check_call_exit(row, prev):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row, prev):
            state["position"] = "put"
            save_last_signal(state)
            return time, "🔁 反手 Put：Call 結構破壞 + Put 入場條件成立"
        return time, "⚠️ Call 出場訊號"

    elif current_pos == "put" and check_put_exit(row, prev):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row, prev):
            state["position"] = "call"
            save_last_signal(state)
            return time, "🔁 反手 Call：Put 結構破壞 + Call 入場條件成立"
        return time, "⚠️ Put 出場訊號"

    elif current_pos == "none":
        if check_call_entry(row, prev):
            state["position"] = "call"
            save_last_signal(state)
            return time, "📈 主升浪 Call 入場"
        elif check_put_entry(row, prev):
            state["position"] = "put"
            save_last_signal(state)
            return time, "📉 主跌浪 Put 入場"

    return None, None

def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未設置，跳過發送")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("發送 Discord 失敗：", e)

def main():
    try:
        df = get_data()
        time, signal = generate_signal(df)
        if signal:
            msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 無信號")
    except Exception as e:
        print("運行異常：", e)

if __name__ == "__main__":
    main()
