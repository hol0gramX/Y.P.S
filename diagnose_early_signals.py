import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ==== 技术指标 ====
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    return df

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=length, d=signal, smooth_k=signal)
    df['K'] = kdj['STOCHk_9_3_3']
    df['D'] = kdj['STOCHd_9_3_3']
    return df

# ==== 数据拉取 ====
def get_data():
    now = datetime.now(tz=EST)
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL, interval="1m", start=start_utc, end=end_utc,
        progress=False, prepost=True, auto_adjust=True
    )
    if df.empty:
        raise ValueError("数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close"])

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)

    return df

# ==== 诊断 ====
def diagnose_indicators():
    df = get_data()
    print(f"✅ 拉取到 {len(df)} 条数据，范围：{df.index[0]} ~ {df.index[-1]}")
    print("=" * 60)

    indicators = ["RSI", "RSI_SLOPE", "EMA20", "MACD", "MACDh", "K", "D"]

    for col in indicators:
        non_na = df[col].notna().sum()
        first_valid = df[col].first_valid_index()
        last_valid = df[col].last_valid_index()
        total = len(df)
        print(f"{col:<8} → 非空 {non_na}/{total} "
              f"({non_na/total:.1%}) | 首个值: {first_valid}, 最后值: {last_valid}")

    print("=" * 60)
    print("📌 最近 5 行数据（含指标）检查：")
    print(df[indicators].tail(5))

if __name__ == "__main__":
    diagnose_indicators()

