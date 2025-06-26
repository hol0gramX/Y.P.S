import yfinance as yf
import pandas as pd
import pandas_ta as ta

def compute_rsi(series, length=6):
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
    df['MACD_slope'] = df['MACDh'].diff().fillna(0)
    return df

def strong_volume(row):
    return float(row['Volume']) >= float(row['Vol_MA5'])

def is_trending_bar(row):
    return float(row['Bar_Size']) > float(row['Bar_Size_MA'])

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
        row['Close'] > row['VWAP'] and
        row['RSI'] > 52 and
        row['MACD_slope'] > 0 and
        row['MACDh'] > 0 and
        strong_volume(row) and
        is_trending_bar(row)
    )

def check_put_entry(row):
    return (
        row['Close'] < row['VWAP'] and
        row['RSI'] < 48 and
        row['MACD_slope'] < 0 and
        row['MACDh'] < 0 and
        strong_volume(row) and
        is_trending_bar(row)
    )

def check_call_exit(row):
    return row['RSI'] < 48 and strong_volume(row)

def check_put_exit(row):
    return row['RSI'] > 52 and strong_volume(row)

def check_pre_call(row):
    return row['RSI'] > 55 and row['MACDh'] > 0 and row['MACD_slope'] > 0

def check_pre_put(row):
    return row['RSI'] < 45 and row['MACDh'] < 0 and row['MACD_slope'] < 0

def is_choppy(row):
    return (
        abs(row['MACD_slope']) < 0.01 and
        row['ATR'] < row['ATR_MA']
    )

def backtest():
    est = "America/New_York"
    df = yf.download("SPY", interval="1m", start="2025-06-25", end="2025-06-26", progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 6).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df).dropna()
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['ATR_MA'] = df['ATR'].rolling(20).mean()
    df['Bar_Size'] = abs(df['Close'] - df['Open'])
    df['Bar_Size_MA'] = df['Bar_Size'].rolling(20).mean()

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


