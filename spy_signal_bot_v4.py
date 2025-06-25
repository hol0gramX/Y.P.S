import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import datetime
import requests

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

def get_data():
    df = yf.download("SPY", interval="1m", period="1d", progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError("下载数据为空，可能是非交易时间或网络问题，请检查")
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

def generate_signals(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None

    # 成交量阈值，用5分钟均量
    vol_threshold = last['Vol_MA5']

    # Call 入场信号（主升浪）
    cond_call_entry = (
        ((last['Close'] > last['VWAP']) or (last['Close'] > last['EMA20'])) and
        (last['EMA5'] > last['EMA10'] > last['EMA20']) and
        (prev['MACD_12_26_9'] < 0 <= last['MACD_12_26_9']) and
        (last['Volume'] >= vol_threshold)
    )

    # Call 出场信号（结构破坏）
    cond_call_exit = (
        (last['Close'] < last['VWAP']) and
        (last['Close'] < last['EMA10']) and
        (last['Low'] < last['PrevLow']) and
        (last['MACDh_12_26_9'] < 0) and
        (last['MACDh_12_26_9'] < prev['MACDh_12_26_9']) and
        (last['Volume'] >= vol_threshold)
    )

    # Put 入场信号（主跌浪）
    cond_put_entry = (
        ((last['Close'] < last['VWAP']) or (last['Close'] < last['EMA20'])) and
        (last['EMA5'] < last['EMA10'] < last['EMA20']) and
        (prev['MACD_12_26_9'] > 0 >= last['MACD_12_26_9']) and
        (last['Volume'] >= vol_threshold)
    )

    # Put 出场信号（结构破坏）
    cond_put_exit = (
        (last['Close'] > last['VWAP']) and
        (last['Close'] > last['EMA10']) and
        (last['High'] > last['PrevHigh']) and
        (last['MACDh_12_26_9'] > 0) and
        (last['MACDh_12_26_9'] > prev['MACDh_12_26_9']) and
        (last['Volume'] >= vol_threshold)
    )

    if cond_call_entry:
        signal = "📈 入場訊號（主升浪）：考慮 Buy Call"
    elif cond_call_exit:
        signal = "⚠️ Call 結構破壞（支撐失守）：考慮止損或出場"
    elif cond_put_entry:
        signal = "📉 入場訊號（主跌浪）：考慮 Buy Put"
    elif cond_put_exit:
        signal = "⚠️ Put 結構破壞（壓力突破）：考慮止損或出場"

    return signal

def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未設置，跳過發送")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("Failed to send to Discord:", e)

def main():
    try:
        df = get_data()
        signal = generate_signals(df)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if signal:
            message = f"[{now}] {signal}"
            print(message)
            send_to_discord(message)
        else:
            print(f"[{now}] 无信号")
    except Exception as e:
        print(f"运行异常: {e}")

if __name__ == "__main__":
    main()
