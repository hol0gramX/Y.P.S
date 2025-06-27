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

def is_market_open(dt):
    schedule = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not schedule.empty and schedule.iloc[0]['market_open'].tz_convert(EST).time() <= dt.time() <= schedule.iloc[0]['market_close'].tz_convert(EST).time()

def get_strength_text(level):
    return "强" if level >= 2 else "中" if level == 1 else "弱"

# ========= 状态管理 =========
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": None, "last_signal": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ========= 主程序 =========
start = (datetime.now(tz=EST) - timedelta(days=3)).strftime("%Y-%m-%d")
end = (datetime.now(tz=EST) + timedelta(days=1)).strftime("%Y-%m-%d")
df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)

if df.empty:
    raise Exception("数据获取失败")

df.ta.rsi(length=14, append=True)
df.ta.macd(append=True)
df.dropna(inplace=True)

state = load_state()
position = state["position"]
last_signal = state["last_signal"]

for idx, row in df.iterrows():
    now = idx.tz_convert(EST)
    t = now.time()

    # === 盘后 16:00 清仓 ===
    if t == time(16, 0):
        position = None
        last_signal = None

    # === 跳过盘前盘后信号判断，仅采集数据 ===
    if time(4, 30) <= t < time(9, 30) or time(16, 0) <= t < time(20, 0):
        continue

    # === 指标 ===
    rsi = row['RSI_14']
    macd = row['MACD_12_26_9']
    macdh = row['MACDh_12_26_9']

    # === 信号强度判断函数（示例） ===
    def get_signal_strength():
        score = 0
        if abs(macdh) > 0.3: score += 1
        if 50 < rsi < 70: score += 1
        elif 30 < rsi <= 50: score += 0.5
        return int(score)

    signal_strength = get_signal_strength()
    strength_text = get_strength_text(signal_strength)
    ts = now.strftime("%Y-%m-%d %H:%M:%S")

    # === 示例信号逻辑 ===
    if position is None:
        if macdh > 0.1 and rsi > 50:
            position = "call"
            print(f"[{ts}] 📈 主升浪 Call 入场（{strength_text}）")
        elif macdh < -0.1 and rsi < 50:
            position = "put"
            print(f"[{ts}] 📉 主跌浪 Put 入场（{strength_text}）")
    elif position == "call" and macdh < 0:
        print(f"[{ts}] ⚠️ Call 出场信号（{strength_text}）")
        position = None
    elif position == "put" and macdh > 0:
        print(f"[{ts}] ⚠️ Put 出场信号（{strength_text}）")
        position = None

save_state({"position": position, "last_signal": last_signal})

