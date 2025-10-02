# debug_open_data.py
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ==== 技术指标 ====
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df["MACD"] = macd["MACD_5_10_20"].fillna(0)
    df["MACDs"] = macd["MACDs_5_10_20"].fillna(0)
    df["MACDh"] = macd["MACDh_5_10_20"].fillna(0)
    return df

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df["High"], df["Low"], df["Close"], k=length, d=signal, smooth_k=signal)
    df["K"] = kdj["STOCHk_9_3_3"].fillna(50)
    df["D"] = kdj["STOCHd_9_3_3"].fillna(50)
    return df

# ==== 拉取数据 ====
def get_data():
    # 固定获取 2025-10-01 当天的数据
    start_utc = datetime(2025, 10, 1, 4, 0).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = datetime(2025, 10, 1, 9, 30).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL, interval="1m", start=start_utc, end=end_utc,
        progress=False, prepost=True, auto_adjust=True
    )

    if df.empty:
        raise ValueError("❌ 没有拉到数据，请检查 yfinance")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close"])

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 技术指标
    df["RSI"] = compute_rsi(df["Close"])
    df["RSI_SLOPE"] = df["RSI"].diff(3)
    df["EMA20"] = ta.ema(df["Close"], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)

    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20", "K", "D"], inplace=True)
    return df

# ==== 打印调试数据 ====
def debug_show_open_data(df):
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 2000)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    # 过滤 2025-10-01 开盘 9:30 前数据
    df_oct1 = df[df.index.date == datetime(2025, 10, 1).date()]
    df_pre_open = df_oct1[df_oct1.index.time < time(9, 30)]

    print("\n=== 📝 2025-10-01 开盘 9:30 前二十条数据 ===")
    cols = ["Close", "RSI", "RSI_SLOPE", "EMA20", "MACD", "MACDh", "K", "D"]
    print(df_pre_open[cols].head(20))

if __name__ == "__main__":
    df = get_data()
    debug_show_open_data(df)

