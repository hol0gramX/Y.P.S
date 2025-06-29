import os
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta

# ========== 常量 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========== 时间函数 ==========
def get_est_now():
    return datetime.now(tz=EST)

# ========== RSI 计算 ==========
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

# ========== MACD 计算并调试列名 ==========
def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    print("🧪 MACD 输出列名:", macd.columns.tolist())
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

# ========== 获取数据并调试 ==========
def get_data():
    now = get_est_now()
    start_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    end_time = now

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_time.astimezone(ZoneInfo("UTC")),
        end=end_time.astimezone(ZoneInfo("UTC")),
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("❌ 数据为空，可能是周末或节假日。")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df = df[(df.index >= start_time) & (df.index < now)]

    df['RSI'] = compute_rsi(df['Close'])
    df = compute_macd(df)
    df.ffill(inplace=True)

    return df

# ========== 主调试入口 ==========
def main():
    print("=" * 60)
    now = get_est_now()
    print(f"🕒 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    try:
        df = get_data()
        print(f"✅ 拉取数据成功，最新时间：{df.index[-1]}")
        print(df.tail(3)[['Close', 'RSI', 'MACD', 'MACDh', 'MACDs']])
    except Exception as e:
        print("[错误]", e)

if __name__ == "__main__":
    main()
