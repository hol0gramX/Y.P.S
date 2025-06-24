
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import time
import requests

# ============ CONFIG ============
import os

DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']

# ============ SIGNAL FUNCTIONS ============

def get_data():
    df = yf.download("SPY", interval="1m", period="1d", progress=False)
    df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
    df['EMA5'] = ta.ema(df['Close'], length=5)
    df['EMA10'] = ta.ema(df['Close'], length=10)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['PrevLow'] = df['Low'].rolling(window=5).min().shift(1)  # 前5根K线最低点，用作支撑
    return df

def generate_signals(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None

    # === Long (Call) Signal ===
    if (last['Close'] > last['VWAP'] > last['EMA20']) and \
       (last['EMA5'] > last['EMA10'] > last['EMA20']) and \
       (last['MACD_12_26_9'] > 0 and last['MACDh_12_26_9'] > prev['MACDh_12_26_9']) and \
       (last['Volume'] > prev['Volume']):
        signal = "📈 入場訊號（主升浪）：考慮 Buy Call"

    # === Stronger Long Exit Signal (加了破前低确认) ===
    elif (
        (last['Close'] < last['VWAP']) and
        (last['Close'] < last['EMA10']) and
        (last['Low'] < last['PrevLow']) and
        (last['MACDh_12_26_9'] < 0 and last['MACDh_12_26_9'] < prev['MACDh_12_26_9']) and
        (last['Volume'] > prev['Volume'])
    ):
     signal = "⚠️ Call 結構破壞（支撐失守）：考慮止損或出場"

    # === Short (Put) Signal ===
    elif (last['Close'] < last['VWAP'] < last['EMA20']) and \
         (last['EMA5'] < last['EMA10'] < last['EMA20']) and \
         (last['MACD_12_26_9'] < 0 and last['MACDh_12_26_9'] < prev['MACDh_12_26_9']) and \
         (last['Volume'] > prev['Volume']):
        signal = "📉 入場訊號（主跌浪）：考慮 Buy Put"

    # === Stronger Short Exit Signal (加了破前高确认) ===
    elif (
        (last['Close'] > last['VWAP']) and
        (last['Close'] > last['EMA10']) and
        (last['High'] > df['High'].rolling(window=5).max().shift(1).iloc[-1]) and
        (last['MACDh_12_26_9'] > 0 and last['MACDh_12_26_9'] > prev['MACDh_12_26_9']) and
        (last['Volume'] > prev['Volume'])
    ):
        signal = "⚠️ Put 結構破壞（壓力突破）：考慮止損或出場"

    return signal

def send_to_discord(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("Failed to send to Discord:", e)

# ============ MAIN LOOP ============

def main():
    df = get_data()
    signal = generate_signals(df)
    if signal:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        message = f"[{now}] {signal}"
        print(message)
        send_to_discord(message)

if __name__ == "__main__":
    print("📡 雙向 SPY 主浪監控（V4支撐確認版）已啟動...")
    while True:
        main()
        time.sleep(60)
