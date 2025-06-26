import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal
import csv
from pathlib import Path

EST = ZoneInfo("America/New_York")
SYMBOL = "SPY"
STATE_FILE = "last_signal.json"
LOG_FILE = "signal_log.csv"
nasdaq = mcal.get_calendar("NASDAQ")

# --------- 工具函数 ---------
def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start_date, end_date):
    schedule = nasdaq.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.tz_localize(None)

def get_market_open_close(date):
    schedule = nasdaq.schedule(start_date=date, end_date=date)
    if schedule.empty:
        return None, None
    open_time = schedule.iloc[0]['market_open'].tz_convert(EST)
    close_time = schedule.iloc[0]['market_close'].tz_convert(EST)
    return open_time, close_time

def is_early_close(date):
    schedule = nasdaq.schedule(start_date=date, end_date=date)
    if schedule.empty:
        return False
    actual_close = schedule.iloc[0]['market_close'].tz_convert(EST)
    normal_close = pd.Timestamp.combine(date, time(16, 0)).tz_localize(EST)
    return actual_close < normal_close

# --------- 指标计算 ---------
def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(length).mean()
    avg_loss = down.rolling(length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def compute_macd(df):
    df = df.copy()
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df

# --------- 数据获取 ---------
def get_data():
    today = datetime(2025, 6, 26).date()
    trade_days = get_trading_days(today - timedelta(days=14), today)
    trade_days = trade_days[trade_days <= pd.Timestamp(today)]
    recent = trade_days[-3:]

    sessions = []
    for d in recent:
        o, c = get_market_open_close(d.date())
        early = is_early_close(d.date())
        sessions.append((o, c, early))

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1] + timedelta(minutes=1)

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_dt.tz_convert('UTC').strftime('%Y-%m-%d %H:%M:%S'),
        end=end_dt.tz_convert('UTC').strftime('%Y-%m-%d %H:%M:%S'),
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]
    df.index = df.index.tz_localize("UTC").tz_convert(EST)

    mask = pd.Series(False, index=df.index)
    for o, c, early in sessions:
        pre = (o - timedelta(hours=5, minutes=30), o)
        mask |= (df.index >= pre[0]) & (df.index < pre[1])
        mask |= (df.index >= o) & (df.index < c)
        if not early:
            post = (c, c + timedelta(hours=4))
            mask |= (df.index >= post[0]) & (df.index < post[1])

    df = df[mask]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# --------- 状态管理 ---------
def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# --------- 日志记录 ---------
def log_signal_to_csv(timestamp, signal):
    file_exists = Path(LOG_FILE).exists()
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal"])
        writer.writerow([timestamp.isoformat(), signal])

# --------- 判断函数 ---------
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']
def macd_trending_up(row): return row['MACD'] > row['MACDs'] and row['MACDh'] > 0
def macd_trending_down(row): return row['MACD'] < row['MACDs'] and row['MACDh'] < 0

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

# --------- 核心信号逻辑 ---------
def generate_signal(row, prev, state):
    current_pos = state.get("position", "none")
    time_est = row.name.tz_convert(EST)

    if current_pos == "call" and check_call_exit(row):
        state["position"] = "none"
        if check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            return time_est, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"
        return time_est, f"⚠️ Call 出场信号"

    elif current_pos == "put" and check_put_exit(row):
        state["position"] = "none"
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            return time_est, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"
        return time_est, f"⚠️ Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            return time_est, f"📈 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            return time_est, f"📉 主跌浪 Put 入场（{strength}）"
        elif allow_call_reentry(row, prev):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            return time_est, f"📈 趋势回补 Call 再入场（{strength}）"
        elif allow_put_reentry(row, prev):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            return time_est, f"📉 趋势回补 Put 再入场（{strength}）"

    return None, None

# --------- 主入口 ---------
def main():
    print(f"[🔁 回测开始] {get_est_now()}")
    try:
        df = get_data()
        state = load_last_signal()
        signal_count = 0

        for i in range(1, len(df)):
            row, prev = df.iloc[i], df.iloc[i - 1]
            time_signal, signal = generate_signal(row, prev, state.copy())
            if signal:
                print(f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S')}] {signal}")
                save_last_signal(state)
                log_signal_to_csv(time_signal, signal)
                signal_count += 1

        if signal_count == 0:
            print("[ℹ️] 当日无交易信号")
        else:
            print(f"[✅] 共记录 {signal_count} 条信号至 signal_log.csv")

    except Exception as e:
        print(f"[❌ 回测失败] {e}")

if __name__ == "__main__":
    main()
