import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def fetch_and_debug():
    # 固定历史时间，确保Yahoo有数据
    start_time = datetime(2023, 6, 26, 4, 0, 0, tzinfo=EST)
    end_time = datetime(2023, 6, 26, 9, 30, 0, tzinfo=EST)

    print(f"Fetching {SYMBOL} data from {start_time} to {end_time} (EST)")

    start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = end_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("数据为空")

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 计算指标
    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20"], inplace=True)

    print(f"\n✅ 成功提取 {len(df)} 条有效数据")
    print("\n📊 最后10条数据（含指标）:")
    print(df.tail(10)[["Close", "EMA20", "RSI", "RSI_SLOPE", "MACD", "MACDh"]])

if __name__ == "__main__":
    fetch_and_debug()
