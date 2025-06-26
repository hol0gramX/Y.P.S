import yfinance as yf
import pandas as pd
import pandas_ta as ta

from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
STATE_FILE = "last_signal_backtest.json"

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
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df

def strong_volume(row):
    return float(row['Volume']) >= float(row['Vol_MA5'])

def macd_trending_up(row):
    return float(row['MACD']) > float(row['MACDs']) and float(row['MACDh']) > 0

def macd_trending_down(row):
    return float(row['MACD']) < float(row['MACDs']) and float(row['MACDh']) < 0

def determine_strength(row, direction):
    strength = "中"
    if direction == "call":
        if float(row['RSI']) > 65 and float(row['MACDh']) > 0.5:
            strength = "强"
        elif float(row['RSI']) < 55:
            strength = "弱"
    elif direction == "put":
        if float(row['RSI']) < 35 and float(row['MACDh']) < -0.5:
            strength = "强"
        elif float(row['RSI']) > 45:
            strength = "弱"
    return strength

def check_call_entry(row):
    return (
        float(row['Close']) > float(row['VWAP']) and
        float(row['RSI']) > 52 and
        strong_volume(row) and
        macd_trending_up(row)
    )

def check_put_entry(row):
    return (
        float(row['Close']) < float(row['VWAP']) and
        float(row['RSI']) < 48 and
        strong_volume(row) and
        macd_trending_down(row)
    )

def check_call_exit(row):
    return float(row['RSI']) < 48 and strong_volume(row)

def check_put_exit(row):
    return float(row['RSI']) > 52 and strong_volume(row)

def load_last_signal():
    return {"position": "none"}

def save_last_signal(state):
    pass  # No file saving for backtest

def backtest():
    est = "America/New_York"
    df = yf.download(SYMBOL, interval="1m", start="2025-06-25", end="2025-06-26", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])

    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df = df.dropna()

    state = load_last_signal()
    results = []

    for idx, row in df.iterrows():
        current_pos = state["position"]

        # 时间转换（统一 EST）
        if idx.tzinfo is None:
            est_time = idx.tz_localize('UTC').tz_convert(est)
        else:
            est_time = idx.tz_convert(est)

        if current_pos == "call" and check_call_exit(row):
            results.append((est_time, "⚠️ Call 出场信号"))
            state["position"] = "none"
            if check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                results.append((est_time, f"🔁 反手 Put 入场（{strength}）"))

        elif current_pos == "put" and check_put_exit(row):
            results.append((est_time, "⚠️ Put 出场信号"))
            state["position"] = "none"
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                results.append((est_time, f"🔁 反手 Call 入场（{strength}）"))

        elif current_pos == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                results.append((est_time, f"📈 主升浪 Call 入场（{strength}）"))
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                results.append((est_time, f"📉 主跌浪 Put 入场（{strength}）"))

    # 打印结果
    for time, signal in results:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}")

if __name__ == "__main__":
    backtest()
