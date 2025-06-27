import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置 =========
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 工具 =========
def get_est_now():
    return datetime.now(tz=EST)

def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": "none"}

def save_last_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ========= 主逻辑 =========
def main():
    today = get_est_now().date()
    start = datetime.combine(today - timedelta(days=2), time(4, 0), tzinfo=EST)
    end = datetime.combine(today + timedelta(days=1), time(20, 0), tzinfo=EST)

    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.index = df.index.tz_localize(None).tz_localize(EST)
    df = df.rename(columns=lambda x: x.lower())

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df["ma20"] = df["close"].rolling(20).mean()
    df["avg_volume"] = df["volume"].rolling(30).mean()

    last_state = {"position": "none"}

    for i in range(34, len(df)):
        now = df.index[i]
        row = df.iloc[i]

        # === 非监控时间（下午16:00后至第二日04:30前）立即清仓 ===
        if (time(16, 0) <= now.time() <= time(23, 59)) or (time(0, 0) <= now.time() < time(4, 30)):
            if last_state["position"] != "none":
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🔒 监控时间清仓 -> {last_state['position']} 站立退场")
                last_state["position"] = "none"
            continue

        # === 开盘前清仓 ===
        if now.time() == time(4, 0):
            last_state["position"] = "none"

        # === 例如：RSI < 30 + MACD 重合进场 Call ===
        signal = None
        if last_state["position"] == "none":
            if row["RSI_14"] < 30 and row["MACDh_12_26_9"] > 0 and row["close"] > row["ma20"]:
                signal = "call"
            elif row["RSI_14"] > 70 and row["MACDh_12_26_9"] < 0 and row["close"] < row["ma20"]:
                signal = "put"
        elif last_state["position"] == "call":
            if row["RSI_14"] > 65 or row["MACDh_12_26_9"] < 0:
                signal = "exit_call"
        elif last_state["position"] == "put":
            if row["RSI_14"] < 35 or row["MACDh_12_26_9"] > 0:
                signal = "exit_put"

        # === 打印日志 ===
        if signal:
            if signal == "call":
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 📈 Call 进场")
                last_state["position"] = "call"
            elif signal == "put":
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 📉 Put 进场")
                last_state["position"] = "put"
            elif signal.startswith("exit"):
                print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ {last_state['position'].capitalize()} 出场")
                last_state["position"] = "none"

if __name__ == "__main__":
    main()

