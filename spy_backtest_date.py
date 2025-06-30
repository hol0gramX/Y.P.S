import yfinance as yf
import pandas as pd
import numpy as np

def download_data():
    # 下载 SPY 1分钟数据，关闭自动复权，只转换时区
    spy = yf.download("SPY", interval="1m", start="2025-06-25", end="2025-06-26", progress=False, auto_adjust=False)
    spy = spy.tz_convert("America/New_York")
    return spy

def calculate_indicators(df):
    # EMA
    df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()

    # MACD
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df

def detect_choppy_segment(df, start_time, end_time, range_threshold=0.003):
    segment = df.loc[start_time:end_time].copy()
    if segment.empty:
        print("❌ 指定时间段没有数据。")
        return

    high = segment['High'].max().item()
    low = segment['Low'].min().item()
    mid = segment['Close'].mean().item()
    price_range = high - low
    range_ratio = price_range / mid

    print(f"\n🔍 检测时间段: {start_time} ~ {end_time}")
    print(f"→ 最高: {high:.2f}, 最低: {low:.2f}, 差值: {price_range:.2f}")
    print(f"→ 区间占比: {range_ratio*100:.2f}%")

    if range_ratio < range_threshold:
        print("✅ 结论：该段为典型震荡带，可过滤。\n")
    else:
        print("🚫 结论：该段波动尚可，不属于高粘合震荡。\n")

    for timestamp, row in segment.iterrows():
        try:
            print(
                f"{timestamp.strftime('%H:%M')} | "
                f"Price: {row['Close']:.2f} | "
                f"EMA5: {row['EMA5']:.2f}, EMA10: {row['EMA10']:.2f}, EMA20: {row['EMA20']:.2f} | "
                f"MACD: {row['MACD']:.4f}, Hist: {row['MACD_hist']:.4f} | "
                f"RSI: {row['RSI']:.2f}"
            )
        except Exception as e:
            print(f"{timestamp.strftime('%H:%M')} | ⚠️ 数据异常: {e}")

def main():
    df = download_data()
    df = calculate_indicators(df)

    start_str = "2025-06-25 11:50"
    end_str = "2025-06-25 12:44"
    start_time = pd.to_datetime(start_str).tz_localize("America/New_York")
    end_time = pd.to_datetime(end_str).tz_localize("America/New_York")

    detect_choppy_segment(df, start_time, end_time)

if __name__ == "__main__":
    main()

