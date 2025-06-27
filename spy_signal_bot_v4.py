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

# --------- 常规配置 ---------
GIST_ID = "7490de39ccc4e20445ef576832bea34b"
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# --------- 日志记录 ---------
def log_signal_to_csv(timestamp, signal):
    date_str = timestamp.strftime("%Y-%m-%d")
    file_name = f"signal_log_{date_str}.csv"
    file_exists = Path(file_name).exists()
    with open(file_name, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "signal"])
        writer.writerow([timestamp.isoformat(), signal])

# --------- Gist 状态管理 ---------
def load_last_signal_from_gist():
    if not GIST_TOKEN:
        return {"position": "none"}
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers={"Authorization": f"token {GIST_TOKEN}"})
        content = r.json()["files"][GIST_FILENAME]["content"]
        return json.loads(content)
    except:
        return {"position": "none"}

def save_last_signal(state):
    if not GIST_TOKEN:
        return
    headers = {"Authorization": f"token {GIST_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    data = {"files": {GIST_FILENAME: {"content": json.dumps(state)}}}
    requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)

load_last_signal = load_last_signal_from_gist

# --------- 时间工具 ---------
def get_est_now():
    return datetime.now(tz=EST)

def get_market_sessions(today):
    trade_days = nasdaq.valid_days(start_date=today - timedelta(days=7), end_date=today)
    recent = trade_days[-2:]
    sch = nasdaq.schedule(start_date=recent[0], end_date=recent[1])
    sessions = []
    for ts in sch.itertuples():
        op = ts.market_open.tz_convert(EST)
        cl = ts.market_close.tz_convert(EST)
        early = cl < pd.Timestamp.combine(ts.Index.date(), time(16)).tz_localize(EST)
        sessions.append((op, cl, early))
    return sessions

def is_market_open_now():
    now = get_est_now()
    sch = nasdaq.schedule(start_date=now.date(), end_date=now.date())
    if sch.empty:
        return False
    market_open = sch.iloc[0]['market_open'].tz_convert(EST)
    market_close = sch.iloc[0]['market_close'].tz_convert(EST)
    return market_open <= now <= market_close

# --------- 技术指标计算 ---------
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

def get_5min_trend():
    df_5min = yf.download(SYMBOL, interval='5m', period='2d', progress=False)
    df_5min = compute_macd(df_5min)
    last = df_5min.iloc[-1]
    if last['MACDh'] > 0.1:
        return "up"
    elif last['MACDh'] < -0.1:
        return "down"
    else:
        return "neutral"

# --------- 数据拉取 ---------
def get_data():
    sessions = get_market_sessions(get_est_now().date())
    start_dt = sessions[0][0] - timedelta(hours=6)
    end_dt = sessions[-1][1] + timedelta(hours=6)

    df = yf.download(SYMBOL, interval="1m", start=start_dt.tz_convert("UTC"), end=end_dt.tz_convert("UTC"),
                     progress=False, prepost=True, auto_adjust=True)

    if df.empty:
        raise ValueError("数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)

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
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "Volume", "VWAP", "RSI", "MACD", "MACDh"], inplace=True)

    print("✅ 最新数据预览：")
    print(df.tail(3)[["Close", "High", "Low", "Volume", "VWAP", "RSI", "MACD", "MACDh"]])
    return df

# --------- 生成信号（原始结构保留） ---------
def generate_signal(df):
    if len(df) < 6:
        return None, None

    row = df.iloc[-1]
    prev_row = df.iloc[-2]
    state = load_last_signal()
    current_pos = state.get("position", "none")
    time_index_est = row.name.tz_convert(EST)
    trend_5min = get_5min_trend()

    if current_pos == "call" and (row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05)):
        state["position"] = "none"
        save_last_signal(state)
        if (row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and row['Volume'] >= row['Vol_MA5']):
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Put：Call 结构破坏 + Put 入场（5min趋势：{trend_5min}）"
        return time_index_est, f"⚠️ Call 出场信号（5min趋势：{trend_5min}）"

    elif current_pos == "put" and (row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05)):
        state["position"] = "none"
        save_last_signal(state)
        if (row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and row['Volume'] >= row['Vol_MA5']):
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Call：Put 结构破坏 + Call 入场（5min趋势：{trend_5min}）"
        return time_index_est, f"⚠️ Put 出场信号（5min趋势：{trend_5min}）"

    elif current_pos == "none":
        if (row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and row['Volume'] >= row['Vol_MA5']):
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"📈 主升浪 Call 入场（5min趋势：{trend_5min}）"
        elif (row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and row['Volume'] >= row['Vol_MA5']):
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"📉 主跌浪 Put 入场（5min趋势：{trend_5min}）"

    return None, None

# --------- Discord 推送 ---------
def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("[通知] DISCORD_WEBHOOK_URL 未设置")
        return
    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

# --------- 主流程 ---------
def main():
    try:
        now = get_est_now()
        print("=" * 60)
        print(f"🕒 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        state = load_last_signal()
        print(f"📦 当前仓位状态：{state.get('position', 'none')}")
        print("-" * 60)

        df = get_data()
        time_signal, signal = generate_signal(df)

        if signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
            log_signal_to_csv(time_signal, signal)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ❎ 无交易信号")

    except Exception as e:
        print("[错误]", e)

if __name__ == "__main__":
    main()
