import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========== 全局配置 ========== 
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========== 数据拉取诊断 ========== 
def diagnose_data_pull():
    try:
        now = datetime.now(tz=EST)
        start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)  # 4点开始
        end_time = now.replace(hour=11, minute=35, second=0, microsecond=0)  # 11:35结束

        print(f"尝试拉取数据时间区间: {start_time} 到 {end_time}")

        start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # 拉取数据
        df = yf.download(
            SYMBOL, interval="1m", start=start_utc, end=end_utc,
            progress=False, prepost=True, auto_adjust=True
        )

        # 检查数据是否为空
        if df.empty:
            print(f"[错误] 拉取的数据为空: {start_utc} 到 {end_utc}")
        else:
            print(f"成功获取数据：{df.head()}")  # 打印前几行数据查看

    except Exception as e:
        print(f"[错误] 拉取数据时发生错误：{e}")

if __name__ == "__main__":
    diagnose_data_pull()

