import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

# 模拟测试用：2025年6月26日 04:00 到 09:30（美东时间）
EST = ZoneInfo("America/New_York")
SYMBOL = "SPY"

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
    # 设置时间区间
    start_est = datetime(2025, 6, 26, 4, 0, tzinfo=EST)
    end_est = datetime(2025, 6, 26, 9, 30, tzinfo=EST)

    # 转换为 UTC，因为 yfinance 接口使用 UTC
    start_utc = start_est.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = end_est.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    print(f"Fetching {SYMBOL} data from {start_est} to {end_est} (EST)")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        prepost=True,
        auto_adjust=True,
        progress=False
    )

    if df.empty:
        print("❌ 无数据，请检查网络或该时间段是否存在交易数据")
        return

    # 转换时区
    df.index = df.index.tz_localize("UTC").tz_convert(EST)

    # 指标计算
    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20"], inplace=True)

    print(f"\n✅ 提取到 {len(df)} 条有效数据")
    print("\n📊 最后10条数据（含指标）:")
    print(df.tail(10)[["Close", "EMA20", "RSI", "RSI_SLOPE", "MACD", "MACDh"]])

if __name__ == "__main__":
    fetch_and_debug()

