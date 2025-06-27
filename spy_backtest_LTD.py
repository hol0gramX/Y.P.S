import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# ========= 配置区域 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
START_DATE = "2025-06-25"
END_DATE = "2025-06-28"

# ========= 工具函数 =========
def get_est_now():
    return datetime.now(tz=EST)

def is_market_open(ts):
    est_time = ts.astimezone(EST)
    t = est_time.time()
    return time(9, 30) <= t <= time(16, 0)

def is_post_or_premarket(ts):
    est_time = ts.astimezone(EST)
    t = est_time.time()
    return (time(16, 0) <= t <= time(20, 0)) or (time(4, 30) <= t <= time(9, 30))

# ========= 主逻辑 =========
def main():
    start = pd.Timestamp(START_DATE).tz_localize(EST)
    end = pd.Timestamp(END_DATE).tz_localize(EST)
    
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)

    # 修复 MultiIndex 列名问题
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = df.columns.map(str.lower)

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.sma(length=20, append=True)

    df = df.dropna().copy()
    df["position"] = ""

    last_signal = None
    position = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = row.name.tz_localize(None).replace(tzinfo=EST)

        # 自动清仓机制（每天下午 16:00 之后立即清仓）
        if ts.time() >= time(16, 0) and position:
            print(f"[{ts}] ⚠️ {position} 出场信号（强）")
            position = None
            continue

        # 在盘后和盘前只采集指标，不进行入场判断
        if is_post_or_premarket(ts):
            continue

        if position is None:
            if row["rsi_14"] < 30 and row["macdh_12_26_9"] > 0 and row["close"] > row["sma_20"]:
                print(f"[{ts}] 📈 主升浪 Call 入场（强）")
                position = "Call"
            elif row["rsi_14"] > 70 and row["macdh_12_26_9"] < 0 and row["close"] < row["sma_20"]:
                print(f"[{ts}] 📉 主跌浪 Put 入场（强）")
                position = "Put"
        elif position == "Call":
            if row["rsi_14"] > 65 or row["macdh_12_26_9"] < 0:
                print(f"[{ts}] ⚠️ Call 出场信号（强）")
                position = None
        elif position == "Put":
            if row["rsi_14"] < 35 or row["macdh_12_26_9"] > 0:
                print(f"[{ts}] ⚠️ Put 出场信号（强）")
                position = None

if __name__ == "__main__":
    main()

