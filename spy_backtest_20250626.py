import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

# --------- 常规配置 ---------
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# --------- 时间工具 ---------
def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start_date, end_date):
    schedule = nasdaq.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.tz_localize(None)

def get_market_open_close(date):
    schedule = nasdaq.schedule(start_date=date, end_date=date)
    if schedule.empty:
        return None, None
    market_open = schedule.iloc[0]['market_open'].tz_convert(EST)
    market_close = schedule.iloc[0]['market_close'].tz_convert(EST)
    return market_open, market_close

def is_early_close(date):
    schedule = nasdaq.schedule(start_date=date, end_date=date)
    if schedule.empty:
        return False
    normal_close = pd.Timestamp.combine(date, time(16, 0)).tz_localize(EST)
    actual_close = schedule.iloc[0]['market_close'].tz_convert(EST)
    return actual_close < normal_close

# --------- 技术指标 ---------
def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(window=length).mean()
    avg_loss = down.rolling(window=length).mean()
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
    trading_days = get_trading_days(today - timedelta(days=14), today)
    recent_days = trading_days[trading_days <= pd.Timestamp(today)].tolist()[-3:]

    sessions = []
    for d in recent_days:
        op, cl = get_market_open_close(d.date())
        early = is_early_close(d.date())
        sessions.append({'open': op, 'close': cl, 'early_close': early})

    start_dt = sessions[0]['open']
    end_dt = sessions[-1]['close'] + timedelta(seconds=1)

    yf_start = start_dt.astimezone(ZoneInfo("UTC")).replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
    yf_end = end_dt.astimezone(ZoneInfo("UTC")).replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

    print(f"[DEBUG] 下载数据：{yf_start} ~ {yf_end}")

    df = yf.download(SYMBOL, interval="1m", start=yf_start, end=yf_end, progress=False, prepost=True, auto_adjust=True)

    if df.empty:
        raise ValueError("下载失败或数据为空")

    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]
    df.index = df.index.tz_localize('UTC').tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)

    mask = pd.Series(False, index=df.index)
    for sess in sessions:
        op, cl = sess['open'], sess['close']
        pm_start, pm_end = op - timedelta(hours=5, minutes=30), op
        mask |= (df.index >= pm_start) & (df.index < cl + timedelta(hours=4))

    df = df[mask]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# --------- 信号判断 ---------
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']
def macd_up(row): return row['MACD'] > row['MACDs'] and row['MACDh'] > 0

def determine_strength(row, direction):
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5: return "强"
        elif row['RSI'] < 55: return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5: return "强"
        elif row['RSI'] > 45: return "弱"
    return "中"

def check_call_entry(row): return row['Close'] > row['VWAP'] and row['RSI'] > 52 and strong_volume(row) and macd_up(row)
def check_put_entry(row): return row['Close'] < row['VWAP'] and row['RSI'] < 48 and strong_volume(row) and not macd_up(row)
def check_call_exit(row): return row['RSI'] < 48 and strong_volume(row)
def check_put_exit(row): return row['RSI'] > 52 and strong_volume(row)

# --------- 状态读取保存 ---------
def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# --------- 信号生成 ---------
def generate_signal(df):
    if len(df) < 6:
        return None, None
    row = df.iloc[-1]
    state = load_last_signal()
    pos = state.get("position", "none")
    ts = row.name.tz_convert(EST)

    if pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            state["position"] = "put"
            save_last_signal(state)
            return ts, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{determine_strength(row, 'put')}）"
        return ts, "⚠️ Call 出场信号"

    if pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            state["position"] = "call"
            save_last_signal(state)
            return ts, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{determine_strength(row, 'call')}）"
        return ts, "⚠️ Put 出场信号"

    if pos == "none":
        if check_call_entry(row):
            state["position"] = "call"
            save_last_signal(state)
            return ts, f"📈 主升浪 Call 入场（{determine_strength(row, 'call')}）"
        elif check_put_entry(row):
            state["position"] = "put"
            save_last_signal(state)
            return ts, f"📉 主跌浪 Put 入场（{determine_strength(row, 'put')}）"

    return None, None

# --------- 主流程 ---------
def main():
    print(f"[🔁 回测开始] {get_est_now()}")
    try:
        df = get_data()
        ts, signal = generate_signal(df)
        if ts and signal:
            print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] {signal}")
        else:
            print("[✅ 回测完成] 无信号")
    except Exception as e:
        print(f"[❌ 回测失败] {e}")

if __name__ == "__main__":
    main()

