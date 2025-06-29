import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def get_sample_data():
    # 使用最近5个交易日数据避免周末无数据问题
    df = yf.download(
        SYMBOL,
        interval="1m",
        period="5d",
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("❌ 没有获取到任何数据（可能是网络问题或 symbol 写错）")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]

    # 加 EST 时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 取最近的300条用于调试（大约半天内）
    return df.tail(300)

def compute_macd(df):
    macd = ta.macd(df["Close"], fast=5, slow=10, signal=20)
    print("🧪 MACD 列名:", macd.columns.tolist())

    df["MACD"] = macd["MACD_5_10_20"].fillna(0)
    df["MACDs"] = macd["MACDs_5_10_20"].fillna(0)
    df["MACDh"] = macd["MACDh_5_10_20"].fillna(0)
    return df

def compute_rsi(df):
    delta = df["Close"].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(14).mean() / down.rolling(14).mean()
    df["RSI"] = (100 - 100 / (1 + rs)).fillna(50)
    return df

def main():
    print("=" * 60)
    print("🧪 调试模式（支持盘后/周末）")
    try:
        df = get_sample_data()
        print(f"✅ 数据获取成功：共 {len(df)} 条")
        df = compute_rsi(df)
        df = compute_macd(df)
        print(df.tail(5)[["Close", "RSI", "MACD", "MACDh", "MACDs"]])
    except Exception as e:
        print("[❌ 错误]", e)

if __name__ == "__main__":
    main()

