import os
import json
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal
import csv

SYMBOL = "SPY"
STATE_FILE = "last_signal.json"
LOG_FILE = "signal_log.csv"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

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

def get_data():
    today = pd.Timestamp("2025-06-26")
    trade_days = get_trading_days(today - timedelta(days=14), today)
    trade_days = trade_days[trade_days <= pd.Timestamp(today)]
    recent = trade_days[-3:]

    sessions = []
    for d in recent:
        op, cl = get_market_open_close(d.date())
        early = is_early_close(d.date())
        sessions.append((op, cl, early))

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1] + timedelta(seconds=1)

    df = yf.download(SYMBOL, interval="1m", start=start_dt.tz_convert('UTC'), end=end_dt.tz_convert('UTC'), progress=False, prepost=True, auto_adjust=True)
    df.index = df.index.tz_localize(None).tz_localize('UTC').tz_convert(EST)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def log_signal_to_csv(timestamp, signal):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal"])
        writer.writerow([timestamp.isoformat(), signal])

def generate_signal(df):
    if len(df) < 6: return None, None
    row = df.iloc[-1]
    prev = df.iloc[-2]
    state = load_last_signal()
    pos = state.get("position", "none")
    time_index = row.name

    if pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"
        return time_index, "⚠️ Call 出场信号"
    elif pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"
        return time_index, "⚠️ Put 出场信号"
    elif pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index, f"📈 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index, f"📉 主跌浪 Put 入场（{strength}）"
        elif allow_call_reentry(row, prev):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index, f"📈 趋势回补 Call 再入场（{strength}）"
        elif allow_put_reentry(row, prev):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index, f"📉 趋势回补 Put 再入场（{strength}）"
    return None, None

def main():
    print(f"[🔁 回测开始] {get_est_now()}")
    try:
        df = get_data()
        t, s = generate_signal(df)
        if s:
            print(f"[{t.strftime('%Y-%m-%d %H:%M:%S')}] {s}")
            log_signal_to_csv(t, s)
        else:
            print("[信息] 无交易信号")
    except Exception as e:
        print(f"[❌ 回测失败] {e}")

if __name__ == "__main__":
    main()
