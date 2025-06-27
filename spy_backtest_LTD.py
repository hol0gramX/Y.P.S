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
STATE_FILE = os.path.abspath("last_signal.json")
START_HOUR = 9
START_MINUTE = 30
END_HOUR = 16

# ========= 工具函数 =========
def get_est_now():
    return datetime.now(tz=EST)

def save_last_signal(signal):
    with open(STATE_FILE, "w") as f:
        json.dump(signal, f)

def load_last_signal():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def in_market_hours(ts):
    return ts.time() >= time(9, 30) and ts.time() <= time(16, 0)

def is_pre_or_post_market(ts):
    return (time(16, 0) <= ts.time() <= time(20, 0)) or (time(4, 30) <= ts.time() <= time(9, 30))

def clear_position():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

# ========= 主函数 =========
def main():
    end = get_est_now()
    start = end - timedelta(days=3)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.columns = df.columns.map(str.lower)  # ✅ 修复列名，兼容 pandas_ta 指标生成

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df["ma20"] = df["close"].rolling(20).mean()
    df["avg_volume"] = df["volume"].rolling(30).mean()

    last_signal = load_last_signal()
    position = last_signal["position"] if last_signal else None
    last_signal_time = last_signal["time"] if last_signal else None

    for i, row in df.iterrows():
        timestamp = pd.Timestamp(i).tz_localize(EST)
        if timestamp.time() == time(4, 0):
            clear_position()
            position = None

        if is_pre_or_post_market(timestamp):
            continue  # 盘前盘后只采数据不做判断

        signal = None

        if position is None:
            if row["rsi_14"] < 30 and row["macdh_12_26_9"] > 0 and row["close"] > row["ma20"]:
                signal = f"[{timestamp}] 📈 主升浪 Call 入场"
                position = "call"
            elif row["rsi_14"] > 70 and row["macdh_12_26_9"] < 0 and row["close"] < row["ma20"]:
                signal = f"[{timestamp}] 📉 主跌浪 Put 入场"
                position = "put"

        elif position == "call":
            if row["rsi_14"] > 60 and row["macdh_12_26_9"] < 0:
                signal = f"[{timestamp}] ⚠️ Call 出场信号"
                position = None

        elif position == "put":
            if row["rsi_14"] < 40 and row["macdh_12_26_9"] > 0:
                signal = f"[{timestamp}] ⚠️ Put 出场信号"
                position = None

        if signal:
            print(signal)
            save_last_signal({"position": position, "time": str(timestamp)})

if __name__ == "__main__":
    main()

