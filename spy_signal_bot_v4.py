import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import requests

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

def get_data():
    df = yf.download("SPY", interval="1m", period="1d", progress=False, auto_adjust=True)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])

    df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
    df['EMA5'] = ta.ema(df['Close'], length=5)
    df['EMA10'] = ta.ema(df['Close'], length=10)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['PrevLow'] = df['Low'].rolling(window=5).min().shift(1)
    df['PrevHigh'] = df['High'].rolling(window=5).max().shift(1)
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    return df

def check_call_entry(row, prev):
    return (
        ((row['Close'] > row['VWAP']) or (row['Close'] > row['EMA20'])) and
        (row['EMA5'] > row['EMA10'] > row['EMA20']) and
        (prev['MACD_12_26_9'] < 0 <= row['MACD_12_26_9']) and
        (row['Volume'] >= row['Vol_MA5'])
    )

def check_put_entry(row, prev):
    return (
        ((row['Close'] < row['VWAP']) or (row['Close'] < row['EMA20'])) and
        (row['EMA5'] < row['EMA10'] < row['EMA20']) and
        (prev['MACD_12_26_9'] > 0 >= row['MACD_12_26_9']) and
        (row['Volume'] >= row['Vol_MA5'])
    )

def check_call_exit(row, prev):
    cond1 = (row['Close'] < row['VWAP']) and (row['Close'] < row['EMA10']) and (row['Low'] < row['PrevLow'])
    cond2 = (row['MACDh_12_26_9'] < 0) and (row['MACDh_12_26_9'] < prev['MACDh_12_26_9'])
    cond3 = (row['Volume'] >= row['Vol_MA5'])
    return cond1 and cond2 and cond3

def check_put_exit(row, prev):
    cond1 = (row['Close'] > row['VWAP']) and (row['Close'] > row['EMA10']) and (row['High'] > row['PrevHigh'])
    cond2 = (row['MACDh_12_26_9'] > 0) and (row['MACDh_12_26_9'] > prev['MACDh_12_26_9'])
    cond3 = (row['Volume'] >= row['Vol_MA5'])
    return cond1 and cond2 and cond3

def generate_signal(df):
    if len(df) < 6:
        return None, None

    row = df.iloc[-1]
    prev = df.iloc[-2]
    time = df.index[-1]

    # 先判断是否反转（先 exit 再反手 entry）
    if check_call_exit(row, prev) and check_put_entry(row, prev):
        return time, "🔁 反手 Put：Call 結構破壞 + Put 入場條件成立"
    elif check_put_exit(row, prev) and check_call_entry(row, prev):
        return time, "🔁 反手 Call：Put 結構破壞 + Call 入場條件成立"

    # 如果没有反转信号，判断独立入场
    elif check_call_entry(row, prev):
        return time, "📈 入場訊號（主升浪）：考慮 Buy Call"
    elif check_put_entry(row, prev):
        return time, "📉 入場訊號（主跌浪）：考慮 Buy Put"

    # 如果是出場也提示
    elif check_call_exit(row, prev):
        return time, "⚠️ Call 結構破壞：考慮止損出場"
    elif check_put_exit(row, prev):
        return time, "⚠️ Put 結構破壞：考慮止損出場"

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
