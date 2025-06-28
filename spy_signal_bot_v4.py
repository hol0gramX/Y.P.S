# ========== 引入库 ========== 
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

# ========== 全局配置 ========== 
GIST_ID = "7490de39ccc4e20445ef576832bea34b"
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========== Gist 状态管理 ========== 
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

# ========== 时间工具 ========== 
def get_est_now():
    return datetime.now(tz=EST)

def get_market_sessions(today):
    trade_days = nasdaq.valid_days(start_date=today - timedelta(days=3), end_date=today)
    recent = trade_days[-1:]
    sch = nasdaq.schedule(start_date=recent[0], end_date=recent[0])
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

# ========== 强制清仓机制 ========== 
def force_clear_at_open():
    now = get_est_now()
    if time(9, 30) <= now.time() <= time(9, 31):
        state = load_last_signal()
        if state.get("position", "none") != "none":
            state["position"] = "none"
            save_last_signal(state)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ⏱️ 开盘强制清仓（状态归零）")

def check_market_closed_and_clear():
    now = get_est_now()
    sch = nasdaq.schedule(start_date=now.date(), end_date=now.date())
    if sch.empty:
        return False
    close_time = sch.iloc[0]['market_close'].tz_convert(EST)
    if now > close_time + timedelta(minutes=1):
        state = load_last_signal()
        if state.get("position", "none") != "none":
            state["position"] = "none"
            save_last_signal(state)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ⛔️ 收盘后自动清仓（状态归零）")
        return True
    return False

# ========== 技术指标 ========== 
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

# ========== HA动能衰竭检测 ========== 
def heikin_ashi_warning(df):
    ha = df[['Open', 'High', 'Low', 'Close']].copy()
    ha['HA_Close'] = (ha['Open'] + ha['High'] + ha['Low'] + ha['Close']) / 4
    ha['HA_Open'] = ha['Open']
    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc('HA_Open')] = (ha.iloc[i-1]['HA_Open'] + ha.iloc[i-1]['HA_Close']) / 2
    ha['HA_High'] = ha[['HA_Open', 'HA_Close', 'High']].max(axis=1)
    ha['HA_Low'] = ha[['HA_Open', 'HA_Close', 'Low']].min(axis=1)

    candles = ha.iloc[-4:]
    bodies = abs(candles['HA_Close'] - candles['HA_Open'])
    full_ranges = candles['HA_High'] - candles['HA_Low']
    body_ratio = bodies / full_ranges

    latest = candles.iloc[-1]
    previous = candles.iloc[-2]

    if body_ratio.iloc[-1] < 0.25 and latest['HA_Close'] < previous['HA_Close']:
        return f"🔻 Heikin-Ashi 衰竭顶部（动能减弱）"
    elif body_ratio.iloc[-1] < 0.25 and latest['HA_Close'] > previous['HA_Close']:
        return f"🔺 Heikin-Ashi 反弹底部（动能减弱）"
    return None

# ========== 数据拉取 ========== 
def get_data():
    sessions = get_market_sessions(get_est_now().date())
    start_dt = sessions[0][0] - timedelta(hours=5)
    end_dt = sessions[0][1] + timedelta(hours=2)
    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_dt.tz_convert("UTC"),
        end=end_dt.tz_convert("UTC"),
        progress=False,
        prepost=True,
        auto_adjust=True
    )
    if df.empty:
        raise ValueError("数据为空")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "Volume", "VWAP", "RSI", "MACD", "MACDh"], inplace=True)
    return df

# ========== 主函数 ========== 
def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("[通知] DISCORD_WEBHOOK_URL 未设置")
        return
    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

def log_signal_to_csv(timestamp, signal):
    pass

def main():
    try:
        now = get_est_now()
        print("=" * 60)
        print(f"🕒 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        force_clear_at_open()
        state = load_last_signal()
        print(f"📦 当前仓位状态：{state.get('position', 'none')}")
        print("-" * 60)

        if check_market_closed_and_clear():
            return

        if not is_market_open_now():
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 🕗 盘前/盘后，不进行信号判断")
            return

        df = get_data()
        time_signal, signal = generate_signal(df)

        ha_warn = heikin_ashi_warning(df)
        if ha_warn:
            print(ha_warn)
            send_to_discord(ha_warn)

        if signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ❎ 无交易信号")

    except Exception as e:
        print("[错误]", e)

if __name__ == "__main__":
    main()
