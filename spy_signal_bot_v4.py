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

def check_call_exit(row, prev_row):
    vol_threshold = row['Vol_MA5']
    # 条件1：跌破VWAP、EMA10、跌破前低
    cond1 = (row['Close'] < row['VWAP']) and (row['Close'] < row['EMA10']) and (row['Low'] < row['PrevLow'])
    # 条件2：MACD柱状图为负且持续减小
    cond2 = (row['MACDh_12_26_9'] < 0) and (row['MACDh_12_26_9'] < prev_row['MACDh_12_26_9'])
    # 条件3：成交量放大
    cond3 = (row['Volume'] >= vol_threshold)
    return cond1 and cond2 and cond3

def check_put_exit(row, prev_row, df):
    vol_threshold = row['Vol_MA5']
    cond1 = (row['Close'] > row['VWAP']) and (row['Close'] > row['EMA10']) and (row['High'] > df['PrevHigh'].iloc[-1])
    cond2 = (row['MACDh_12_26_9'] > 0) and (row['MACDh_12_26_9'] > prev_row['MACDh_12_26_9'])
    cond3 = (row['Volume'] >= vol_threshold)
    return cond1 and cond2 and cond3

def generate_signals(df):
    signals = []
    vol_thresholds = df['Vol_MA5']

    # 先计算每根K线是否满足入场/出场条件
    call_entry_flags = []
    call_exit_flags = []
    put_entry_flags = []
    put_exit_flags = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        vol_threshold = row['Vol_MA5']

        # Call 入场信号
        cond_call_entry = (
            ((row['Close'] > row['VWAP']) or (row['Close'] > row['EMA20'])) and
            (row['EMA5'] > row['EMA10'] > row['EMA20']) and
            (prev['MACD_12_26_9'] < 0 <= row['MACD_12_26_9']) and
            (row['Volume'] >= vol_threshold)
        )
        call_entry_flags.append(cond_call_entry)

        # Call 出场信号
        cond_call_exit = check_call_exit(row, prev)
        call_exit_flags.append(cond_call_exit)

        # Put 入场信号
        cond_put_entry = (
            ((row['Close'] < row['VWAP']) or (row['Close'] < row['EMA20'])) and
            (row['EMA5'] < row['EMA10'] < row['EMA20']) and
            (prev['MACD_12_26_9'] > 0 >= row['MACD_12_26_9']) and
            (row['Volume'] >= vol_threshold)
        )
        put_entry_flags.append(cond_put_entry)

        # Put 出场信号
        cond_put_exit = check_put_exit(row, prev, df)
        put_exit_flags.append(cond_put_exit)

    # 追踪状态，只有连续3根K线满足出场条件才触发出场信号
    call_in_position = False
    put_in_position = False

    for i in range(2, len(df)-1):
        time = df.index[i+1]  # 事件发生时间点，用下一根K线时间表示

        # Call 入场
        if not call_in_position and call_entry_flags[i]:
            call_in_position = True
            signals.append((time, "📈 入場訊號（主升浪）：考慮 Buy Call"))

        # Call 出场 - 连续3根满足出场条件
        if call_in_position and all(call_exit_flags[j] for j in range(i-2, i+1)):
            call_in_position = False
            signals.append((time, "⚠️ Call 結構破壞（支撐失守）：考慮止損或出場"))

        # Put 入场
        if not put_in_position and put_entry_flags[i]:
            put_in_position = True
            signals.append((time, "📉 入場訊號（主跌浪）：考慮 Buy Put"))

        # Put 出场 - 连续3根满足出场条件
        if put_in_position and all(put_exit_flags[j] for j in range(i-2, i+1)):
            put_in_position = False
            signals.append((time, "⚠️ Put 結構破壞（壓力突破）：考慮止損或出場"))

    return signals

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
        signals = generate_signals(df)
        for time, signal in signals:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            message = f"[{now}] {signal}"
            print(message)
            send_to_discord(message)
        if not signals:
            print("无信号")
    except Exception as e:
        print(f"运行异常: {e}")

if __name__ == "__main__":
    main()
