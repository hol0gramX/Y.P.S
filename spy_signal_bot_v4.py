import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

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

def is_market_open_now():
    now = get_est_now()
    sch = nasdaq.schedule(start_date=now.date(), end_date=now.date())
    if sch.empty:
        return False
    market_open = sch.iloc[0]['market_open'].tz_convert(EST)
    market_close = sch.iloc[0]['market_close'].tz_convert(EST)
    return market_open <= now <= market_close

# ========== 强制清仓机制 ==========
def force_clear_at_close():
    now = get_est_now()
    if time(15, 59) <= now.time() < time(16, 0):
        state = load_last_signal()
        if state.get("position", "none") != "none":
            state["position"] = "none"
            save_last_signal(state)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] \u23f0 15:59 \u81ea\u52a8\u6e05\u4ed3\uff08\u72b6\u6001\u5f52\u96f6\uff09")

# ========== 数据拉取 ==========
def get_data():
    now = get_est_now()
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("\u6570\u636e\u4e3a\u7a7a")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    df['EMA20'] = ta.ema(df['Close'], length=20)

    df.dropna(subset=["High", "Low", "Close", "RSI", "RSI_SLOPE", "MACD", "MACDh", "EMA20"], inplace=True)
    return df

# ========== 判断逻辑 ==========
def determine_strength(row, direction):
    ema_diff_ratio = (row['Close'] - row['EMA20']) / row['EMA20']
    rsi_slope = row.get('RSI_SLOPE', 0)

    if direction == "call":
        if row['RSI'] >= 60 and row['MACDh'] > 0.3 and ema_diff_ratio > 0.002:
            return "\u5f3a"
        elif row['RSI'] >= 55 and row['MACDh'] > 0 and ema_diff_ratio > 0:
            return "\u4e2d"
        elif row['RSI'] < 50 or ema_diff_ratio < 0:
            return "\u5f31"
        else:
            return "\u4e2d" if rsi_slope > 0.1 else "\u5f31"

    elif direction == "put":
        if row['RSI'] <= 40 and row['MACDh'] < -0.3 and ema_diff_ratio < -0.002:
            return "\u5f3a"
        elif row['RSI'] <= 45 and row['MACDh'] < 0 and ema_diff_ratio < 0:
            return "\u4e2d"
        elif row['RSI'] > 50 or ema_diff_ratio > 0:
            return "\u5f31"
        else:
            return "\u4e2d" if rsi_slope < -0.1 else "\u5f31"

    return "\u4e2d"

def check_call_entry(row):
    return row['Close'] > row['EMA20'] and row['RSI'] > 55 and row['MACDh'] > 0

def check_put_entry(row):
    return row['Close'] < row['EMA20'] and row['RSI'] < 45 and row['MACDh'] < 0

def allow_bottom_rebound_call(row, prev):
    return row['Close'] < row['EMA20'] and row['RSI'] > prev['RSI'] and row['MACDh'] > prev['MACDh'] and row['MACD'] > -0.3

def allow_top_rebound_put(row, prev):
    return row['Close'] > row['EMA20'] and row['RSI'] < prev['RSI'] and row['MACDh'] < prev['MACDh'] and row['MACD'] < 0.3

def check_call_exit(row):
    return row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05)

def check_put_exit(row):
    return row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05)

def is_trend_continuation(row, prev, position):
    if position == "call":
        return row['MACDh'] > 0 and row['RSI'] > 45
    elif position == "put":
        return row['MACDh'] < 0 and row['RSI'] < 55
    return False

# ========== 主信号逻辑 ==========
def generate_signal(df):
    if df.empty or 'MACD' not in df.columns or df['MACD'].isnull().all() or len(df) < 6:
        return None, None

    row = df.iloc[-1]
    prev = df.iloc[-2]
    state = load_last_signal()
    pos = state.get("position", "none")
    now_time = row.name

    if pos == "call" and check_call_exit(row):
        if is_trend_continuation(row, prev, "call"):
            return now_time, f"\u23f3 \u8d8b\u52bf\u4e2d\u7ee7\u8c6a\u514d\uff0cCall \u6301\u4ed3\u4e0d\u51fa\u573a\uff08RSI={row['RSI']:.1f}, MACDh={row['MACDh']:.3f}\uff09"
        strength = determine_strength(row, "call")
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row) or allow_top_rebound_put(row, prev):
            state["position"] = "put"
            strength_put = determine_strength(row, "put")
            save_last_signal(state)
            return now_time, f"\ud83d\udd01 反手 Put：Call 结构破坏 + Put 入场（{strength_put}）"
        return now_time, f"\u26a0\ufe0f Call \u51fa\u573a\u4fe1\u53f7\uff08{strength}\uff09"

    elif pos == "put" and check_put_exit(row):
        if is_trend_continuation(row, prev, "put"):
            return now_time, f"\u23f3 \u8d8b\u52bf\u4e2d\u7ee7\u8c6a\u514d\uff0cPut \u6301\u4ed3\u4e0d\u51fa\u573a\uff08RSI={row['RSI']:.1f}, MACDh={row['MACDh']:.3f}\uff09"
        strength = determine_strength(row, "put")
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row) or allow_bottom_rebound_call(row, prev):
            state["position"] = "call"
            strength_call = determine_strength(row, "call")
            save_last_signal(state)
            return now_time, f"\ud83d\udd01 反手 Call：Put 结构破坏 + Call 入场（{strength_call}）"
        return now_time, f"\u26a0\ufe0f Put \u51fa\u573a\u4fe1\u53f7\uff08{strength}\uff09"

    elif pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return now_time, f"\ud83d\udcc8 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return now_time, f"\ud83d\udcc9 主跌浪 Put 入场（{strength}）"
        elif allow_bottom_rebound_call(row, prev):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return now_time, f"\ud83d\udcc8 底部反弹 Call 捕捉（{strength}）"
        elif allow_top_rebound_put(row, prev):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return now_time, f"\ud83d\udcc9 顶部反转 Put 捕捉（{strength}）"

    return None, None

# ========== 通知 ==========
def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("[通知] DISCORD_WEBHOOK_URL 未设置")
        return
    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

# ========== 主函数 ==========
def main():
    try:
        now = get_est_now()
        print("=" * 60)
        print(f"\ud83d\udd52 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        force_clear_at_close()

        state = load_last_signal()
        print(f"\ud83d\udce6 当前仓位状态：{state.get('position', 'none')}")
        print("-" * 60)

        if not is_market_open_now():
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] \ud83d\udd57 盘前/盘后，不进行信号判断")
            return

        df = get_data()
        time_signal, signal = generate_signal(df)
        if signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] \u274e 无交易信号")

    except Exception as e:
        print("[错误]", e)

if __name__ == "__main__":
    main()
