import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)

def debug_fetch_fixed_datetime():
    # 固定时间点：2025年6月27日 09:30 EST
    fixed_now = datetime(2025, 6, 27, 9, 30, tzinfo=EST)
    start_time = fixed_now.replace(hour=4, minute=0, second=0, microsecond=0)

    print(f"模拟当前时间（EST）: {fixed_now}")
    print(f"开始拉取时间（EST）: {start_time}")

    start_utc = start_time.astimezone(ZoneInfo("UTC"))
    end_utc = fixed_now.astimezone(ZoneInfo("UTC"))

    print(f"开始拉取时间（UTC）: {start_utc}")
    print(f"结束拉取时间（UTC）: {end_utc}")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    print(f"拉取数据条数: {len(df)}")
    if df.empty:
        print("数据为空")
        return

    # 计算VWAP
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    # 计算RSI
    df['RSI'] = compute_rsi(df['Close'])

    # 保证索引为EST时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    print(f"数据索引时区: {df.index.tz}")
    print("最近5条数据：")
    print(df[['Open', 'High', 'Low', 'Close', 'Volume', 'VWAP', 'RSI']].tail(5))

if __name__ == "__main__":
    debug_fetch_fixed_datetime()

