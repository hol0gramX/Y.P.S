import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import time
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
    pass  # Backtest 不存文件

def backtest():
    est = ZoneInfo("America/New_York")

    # 下载包含盘前盘后数据
    df = yf.download(
        SYMBOL,
        interval="1m",
        start="2025-06-24",
        end="2025-06-26",
        progress=False,
        prepost=True
    )
    # 转换时区
    df.index = df.index.tz_localize('UTC').tz_convert(est)

    # 过滤 6月24日16:00-20:00盘后 和 6月25日4:00开始的盘前盘中盘后
    df_filtered = pd.concat([
        df.loc[
            (df.index.date == pd.to_datetime("2025-06-24").date()) &
            (df.index.time >= time(16, 0)) & (df.index.time <= time(20, 0))
        ],
        df.loc[
            (df.index.date == pd.to_datetime("2025-06-25").date()) &
            (df.index.time >= time(4, 0))
        ]
    ]).sort_index()

    # 计算指标
    df_filtered['Vol_MA5'] = df_filtered['Volume'].rolling(5).mean()
    df_filtered['RSI'] = compute_rsi(df_filtered['Close'], 14).fillna(50)
    df_filtered['VWAP'] = (df_filtered['Close'] * df_filtered['Volume']).cumsum() / df_filtered['Volume'].cumsum()
    df_filtered = compute_macd(df_filtered)
    df_filtered = df_filtered.dropna()

    state = load_last_signal()
    results = []

    for idx, row in df_filtered.iterrows():
        current_pos = state["position"]

        est_time = idx  # 已是美东时间

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

    for time, signal in results:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}")

if __name__ == "__main__":
    backtest()


