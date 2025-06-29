import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import pandas_ta as ta  # 用pandas_ta来算MACD等更方便

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def get_est_now_fake():
    return datetime(2025, 6, 27, 9, 30, 0, tzinfo=EST)

def get_data_debug():
    now = get_est_now_fake()
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC"))
    end_utc = now.astimezone(ZoneInfo("UTC"))

    print(f"模拟当前时间（EST）: {now}")
    print(f"开始拉取时间（EST）: {start_time}")
    print(f"开始拉取时间（UTC）: {start_utc}")
    print(f"结束拉取时间（UTC）: {end_utc}")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=False
    )

    if df.empty:
        print("数据为空")
        return None

    print(f"拉取数据条数: {len(df)}")
    print(f"数据索引时区（raw）: {df.index.tz}")
    # 转为 EST
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    print(f"数据索引时区（转为EST后）: {df.index.tz}")

    # --- 计算指标 ---
    # RSI
    df['RSI'] = compute_rsi(df['Close'])
    # RSI_SLOPE (3分钟差分)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    # MACD 使用 pandas_ta
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    # VWAP
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    print("最近5条成交量：")
    print(df['Volume'].tail(5))

    print("最近5条指标数据：")
    print(df.tail(5)[['Close', 'RSI', 'RSI_SLOPE', 'MACD', 'MACDs', 'MACDh', 'VWAP']])

    return df

if __name__ == "__main__":
    get_data_debug()

