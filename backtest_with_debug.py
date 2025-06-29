import yfinance as yf
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def get_est_now_fake():
    # 模拟时间 2025-06-27 09:30:00 EST
    return datetime(2025, 6, 27, 9, 30, 0, tzinfo=EST)

def get_data_debug():
    now = get_est_now_fake()
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC"))
    end_utc = now.astimezone(ZoneInfo("UTC"))

    start_str = start_utc.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_utc.strftime('%Y-%m-%d %H:%M:%S')

    print(f"模拟当前时间（EST）: {now}")
    print(f"开始拉取时间（EST）: {start_time}")
    print(f"开始拉取时间（UTC）: {start_str}")
    print(f"结束拉取时间（UTC）: {end_str}")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_str,
        end=end_str,
        progress=False,
        prepost=True,
        auto_adjust=False  # 关闭自动调整
    )

    if df.empty:
        print("数据为空")
        return None

    print(f"拉取数据条数: {len(df)}")
    print(f"数据索引时区（raw）: {df.index.tz}")
    # 统一转为 EST 时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    print(f"数据索引时区（转为EST后）: {df.index.tz}")

    # 先看下成交量，确认非0
    print("最近5条成交量：")
    print(df['Volume'].tail(5))
    # 看几列价格和成交量
    print("最近5条数据：")
    print(df.tail(5)[['Open', 'High', 'Low', 'Close', 'Volume']])
    return df

if __name__ == "__main__":
    get_data_debug()

