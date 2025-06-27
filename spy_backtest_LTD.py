import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置区域 =========
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 工具函数 =========
def get_est_now():
    return datetime.now(tz=EST)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": "none", "last_entry_time": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def is_market_hours(ts):
    dt = pd.Timestamp(ts).tz_localize(None)
    return time(9, 30) <= dt.time() <= time(16, 0)

def in_forbidden_time(ts):
    est = pd.Timestamp(ts).tz_localize("America/New_York")
    t = est.time()
    return (time(16, 0) <= t < time(20, 0)) or (time(4, 30) <= t < time(9, 30))

def get_signal_strength(rsi, macd, volume, avg_volume):
    score = 0
    if rsi > 60: score += 1
    if macd > 0: score += 1
    if volume > avg_volume: score += 1
    if score == 3: return "强"
    if score == 2: return "中"
    return "弱"

def reset_position_if_needed(df, state):
    for i, row in df.iterrows():
        ts = row.name
        if ts.time() == time(16, 0):
            state["position"] = "none"
            state["last_entry_time"] = None

def log_signal(ts, message):
    print(f"[{ts}] {message}")
    with open("signal_log_backtest.csv", "a") as f:
        f.write(f"{ts},{message}\n")

def main():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.dropna(inplace=True)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.ema(length=20, append=True)
    df["avg_volume"] = df["volume"].rolling(30).mean()

    state = load_state()
    reset_position_if_needed(df, state)

    for i in range(30, len(df)):
        row = df.iloc[i]
        ts = row.name

        if in_forbidden_time(ts):
            continue

        rsi = row["RSI_14"]
        macd = row["MACD_12_26_9"]
        macdh = row["MACDh_12_26_9"]
        volume = row["volume"]
        avg_volume = row["avg_volume"]
        close = row["close"]

        signal_strength = get_signal_strength(rsi, macd, volume, avg_volume)
        trend = "增强" if macdh > 0.1 else ("减弱" if macdh < -0.1 else "震荡")

        if state["position"] == "none":
            if macdh > 0.1 and rsi > 50:
                log_signal(ts, f"📈 主升浪 Call 入场（{signal_strength}，趋势：{trend}）")
                state["position"] = "call"
                state["last_entry_time"] = str(ts)
            elif macdh < -0.1 and rsi < 50:
                log_signal(ts, f"📉 主跌浪 Put 入场（{signal_strength}，趋势：{trend}）")
                state["position"] = "put"
                state["last_entry_time"] = str(ts)
        elif state["position"] == "call":
            if rsi < 55 or macdh < 0:
                log_signal(ts, f"⚠️ Call 出场信号（{signal_strength}）")
                state["position"] = "none"
                if macdh < -0.1 and rsi < 50:
                    log_signal(ts, f"📉 主跌浪 Put 入场（{signal_strength}，趋势：{trend}）")
                    state["position"] = "put"
                    state["last_entry_time"] = str(ts)
        elif state["position"] == "put":
            if rsi > 45 or macdh > 0:
                log_signal(ts, f"⚠️ Put 出场信号（{signal_strength}）")
                state["position"] = "none"
                if macdh > 0.1 and rsi > 50:
                    log_signal(ts, f"📈 主升浪 Call 入场（{signal_strength}，趋势：{trend}）")
                    state["position"] = "call"
                    state["last_entry_time"] = str(ts)

    save_state(state)

if __name__ == "__main__":
    main()

