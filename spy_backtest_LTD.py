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

def est_timestamp(ts):
    return ts.tz_convert(EST).replace(tzinfo=None)

def is_market_open(dt):
    schedule = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    if schedule.empty:
        return False
    market_open = schedule.iloc[0]['market_open'].tz_convert(EST).time()
    market_close = schedule.iloc[0]['market_close'].tz_convert(EST).time()
    return market_open <= dt.time() <= market_close

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": "none"}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ========= 主函数 =========
def main():
    now = get_est_now()
    start = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.index = df.index.tz_localize("UTC").tz_convert(EST)

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.sma(length=20, append=True)

    state = load_state()
    position = state.get("position", "none")

    last_date = None

    for timestamp, row in df.iterrows():
        ts = timestamp
        if ts.time() >= time(16, 0):
            position = "none"
            continue
        if time(4, 0) <= ts.time() < time(9, 30):
            continue

        if last_date != ts.date():
            position = "none"
            last_date = ts.date()

        rsi = row.get("RSI_14")
        macdh = row.get("MACDh_12_26_9")
        close = row.get("Close")
        ma20 = row.get("SMA_20")

        if rsi is None or macdh is None or close is None or ma20 is None:
            continue

        if position == "none":
            if rsi < 30 and macdh > 0 and close > ma20:
                print(f"[{ts}] 📈 主升浪 Call 入场（强）")
                position = "call"
            elif rsi > 70 and macdh < 0 and close < ma20:
                print(f"[{ts}] 📉 主跌浪 Put 入场（强）")
                position = "put"

        elif position == "call":
            if rsi > 70 or macdh < 0:
                print(f"[{ts}] ⚠️ Call 出场信号（强）")
                position = "none"

        elif position == "put":
            if rsi < 30 or macdh > 0:
                print(f"[{ts}] ⚠️ Put 出场信号（强）")
                position = "none"

    save_state({"position": position})

if __name__ == "__main__":
    main()

