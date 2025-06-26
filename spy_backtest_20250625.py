import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal
from pathlib import Path
import csv

# ----------------- 基本配置 -----------------
STATE_FILE = os.path.abspath("last_signal.json")
LOG_FILE = "signal_log.csv"
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ----------------- 日志函数 -----------------
def log_signal_to_csv(timestamp, signal):
    file_exists = Path(LOG_FILE).exists()
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal"])
        writer.writerow([timestamp.isoformat(), signal])

# ----------------- 状态管理 -----------------
def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ----------------- 时间与数据 -----------------
def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start, end):
    return nasdaq.schedule(start_date=start, end_date=end).index.tz_localize(None)

def get_market_open_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty: return None, None
    return sch.iloc[0]['market_open'].tz_convert(EST), sch.iloc[0]['market_close'].tz_convert(EST)

def is_early_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    return not sch.empty and sch.iloc[0]['market_close'].tz_convert(EST) < pd.Timestamp.combine(d, time(16, 0)).tz_localize(EST)

def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df

def get_data():
    today = pd.Timestamp("2025-06-26").date()
    trade_days = get_trading_days(today - timedelta(days=14), today)
    recent = trade_days[-3:]
    sessions = [(get_market_open_close(d.date())[0], get_market_open_close(d.date())[1], is_early_close(d.date())) for d in recent]

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1]
    df = yf.download(SYMBOL, interval="1m", start=start_dt.tz_convert('UTC'), end=end_dt.tz_convert('UTC'), progress=False, prepost=True, auto_adjust=True)
    df = df.dropna(subset=['High','Low','Close','Volume'])
    df = df[df['Volume'] > 0]
    df.index = df.index.tz_convert(EST)

    mask = pd.Series(False, index=df.index)
    for op, cl, early in sessions:
        intervals = [(op - timedelta(hours=5, minutes=30), op), (op, cl)]
        if not early:
            intervals.append((cl, cl + timedelta(hours=4)))
        for s, e in intervals:
            mask |= (df.index >= s) & (df.index < e)

    df = df[mask]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# ----------------- 信号逻辑 -----------------
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']
def determine_strength(row, direction):
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5: return "强"
        elif row['RSI'] < 55: return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5: return "强"
        elif row['RSI'] > 45: return "弱"
    return "中"

def check_call_entry(row): return row['Close'] > row['VWAP'] and row['RSI'] > 50 and row['MACDh'] > -0.1 and strong_volume(row)
def check_put_entry(row): return row['Close'] < row['VWAP'] and row['RSI'] < 51 and row['MACDh'] < 0.15 and strong_volume(row)
def check_call_exit(row): return row['RSI'] < 48 and strong_volume(row)
def check_put_exit(row): return row['RSI'] > 52 and strong_volume(row)
def allow_call_reentry(row, prev): return prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACDh'] > 0.1 and strong_volume(row)
def allow_put_reentry(row, prev): return prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACDh'] < 0.05 and strong_volume(row)

def run_backtest(df):
    state = {"position": "none"}
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        ts = row.name
        current_pos = state.get("position", "none")

        if current_pos == "call" and check_call_exit(row):
            state["position"] = "none"
            if check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                log_signal_to_csv(ts, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）")
            else:
                log_signal_to_csv(ts, "⚠️ Call 出场信号")

        elif current_pos == "put" and check_put_exit(row):
            state["position"] = "none"
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                log_signal_to_csv(ts, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）")
            else:
                log_signal_to_csv(ts, "⚠️ Put 出场信号")

        elif current_pos == "none":
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                log_signal_to_csv(ts, f"📈 主升浪 Call 入场（{strength}）")
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                log_signal_to_csv(ts, f"📉 主跌浪 Put 入场（{strength}）")
            elif allow_call_reentry(row, prev_row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                log_signal_to_csv(ts, f"📈 趋势回补 Call 再入场（{strength}）")
            elif allow_put_reentry(row, prev_row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                log_signal_to_csv(ts, f"📉 趋势回补 Put 再入场（{strength}）")

# ----------------- 主函数 -----------------
def main():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    try:
        df = get_data()
        run_backtest(df)
        print(f"[✅ 回测完成] 所有信号已写入 signal_log.csv")
    except Exception as e:
        print("[❌ 回测失败]", e)

if __name__ == "__main__":
    main()

