import yfinance as yf
import pandas as pd
import pandas_ta as ta

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

def check_pre_call(row):
    return float(row['RSI']) > 55 and float(row['MACDh']) > 0

def check_pre_put(row):
    return float(row['RSI']) < 45 and float(row['MACDh']) < 0

def is_choppy(row):
    return abs(float(row['MACDh'])) < 0.1 and 45 <= float(row['RSI']) <= 55

def backtest():
    est = "America/New_York"
    df = yf.download("SPY", interval="1m", start="2025-06-25", end="2025-06-26", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df).dropna()

    position = "none"
    results = []

    for idx, row in df.iterrows():
        est_time = idx.tz_localize('UTC').tz_convert(est) if idx.tz is None else idx.tz_convert(est)

        if is_choppy(row):
            results.append((est_time, "🚫 垃圾段不做"))
            continue

        if position == "call" and check_call_exit(row):
            results.append((est_time, "⚠️ Call 出场信号"))
            position = "none"
            if check_put_entry(row):
                strength = determine_strength(row, "put")
                position = "put"
                results.append((est_time, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"))

        elif position == "put" and check_put_exit(row):
            results.append((est_time, "⚠️ Put 出场信号"))
            position = "none"
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                position = "call"
                results.append((est_time, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"))

        elif position == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                position = "call"
                results.append((est_time, f"📈 主升浪 Call 入场（{strength}）"))
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                position = "put"
                results.append((est_time, f"📉 主跌浪 Put 入场（{strength}）"))
            elif check_pre_call(row):
                results.append((est_time, "⏳ Call 预备信号"))
            elif check_pre_put(row):
                results.append((est_time, "⏳ Put 预备信号"))

    for time, signal in results:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}")

if __name__ == "__main__":
    backtest()


