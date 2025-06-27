# ========= 配置区域 =========
import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 辅助函数 =========
def get_est_now():
    return datetime.now(tz=EST)

def is_market_open(dt):
    sched = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not sched.empty and sched.iloc[0]['market_open'].tz_convert(EST) <= dt <= sched.iloc[0]['market_close'].tz_convert(EST)

def is_market_day(dt):
    return not nasdaq.schedule(start_date=dt.date(), end_date=dt.date()).empty

def is_regular_hours(dt):
    return time(9, 30) <= dt.time() <= time(16, 0)

def is_post_market(dt):
    return time(16, 0) < dt.time() <= time(20, 0)

def is_pre_market(dt):
    return time(4, 30) <= dt.time() < time(9, 30)

def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ========= 主函数 =========
def main():
    end = get_est_now()
    start = end - timedelta(days=3)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    df.columns = df.columns.str.capitalize()  # 标准化列名

    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df["MA20"] = df["Close"].rolling(20).mean()
    df["avg_volume"] = df["Volume"].rolling(30).mean()

    last_state = {"position": "none", "last_entry_time": None}
    signal_log = []

    for i in range(34, len(df)):
        now = df.index[i].tz_convert(EST)
        row = df.iloc[i]

        # 强制清仓机制
        if is_post_market(now) or is_pre_market(now):
            last_state["position"] = "none"
            continue

        # 非交易日跳过
        if not is_market_day(now):
            continue

        rsi = row['RSI_14']
        macd = row['MACD_12_26_9']
        macdh = row['MACDh_12_26_9']
        close = row['Close']
        ma20 = row['MA20']
        volume = row['Volume']
        avg_volume = row['avg_volume']

        # 简化的判断逻辑（待你融合完整策略）
        if rsi < 30 and macd < 0 and macdh < 0 and close < ma20 and volume > avg_volume:
            if last_state["position"] != "put":
                last_state["position"] = "put"
                signal_log.append([now.strftime("%Y-%m-%d %H:%M:%S"), "📉 主跌浪 Put 入场"])
        elif rsi > 70 and macd > 0 and macdh > 0 and close > ma20 and volume > avg_volume:
            if last_state["position"] != "call":
                last_state["position"] = "call"
                signal_log.append([now.strftime("%Y-%m-%d %H:%M:%S"), "📈 主升浪 Call 入场"])
        elif (rsi > 60 and last_state["position"] == "put") or (rsi < 40 and last_state["position"] == "call"):
            signal_log.append([now.strftime("%Y-%m-%d %H:%M:%S"), "⚠️ {} 出场信号".format(last_state["position"].capitalize())])
            last_state["position"] = "none"

    save_last_state(last_state)
    out_path = "signal_log_backtest.csv"
    pd.DataFrame(signal_log, columns=["timestamp", "signal"]).to_csv(out_path, index=False)
    print(f"[✅ 保存完成] 写入 {out_path} 共 {len(signal_log)} 条信号")

if __name__ == "__main__":
    main()

