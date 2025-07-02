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
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ⏰ 15:59 自动清仓（状态归零）")

# ========== 技术指标 ==========
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

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
        raise ValueError("数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20"], inplace=True)

    return df

# ========== 震荡带判断 ==========
def is_sideways(row, df, idx, window=3, price_threshold=0.002, ema_threshold=0.02):
    if idx < window:
        return False
    price_near = abs(row['Close'] - row['EMA20']) / row['EMA20'] < price_threshold
    ema_now = row['EMA20']
    ema_past = df.iloc[idx - window]['EMA20']
    ema_flat = abs(ema_now - ema_past) < ema_threshold
    return price_near and ema_flat

# ========== 信号判断函数 ==========
def determine_strength(row, direction):
    ema_diff_ratio = (row['Close'] - row['EMA20']) / row['EMA20']
    rsi_slope = row.get('RSI_SLOPE', 0)

    if direction == "call":
        if row['RSI'] >= 60 and row['MACDh'] > 0.3 and ema_diff_ratio > 0.002:
            return "强"
        elif row['RSI'] >= 55 and row['MACDh'] > 0 and ema_diff_ratio > 0:
            return "中"
        elif row['RSI'] < 50 or ema_diff_ratio < 0:
            return "弱"
        else:
            if rsi_slope > 0.1:
                return "中"
            return "弱"

    elif direction == "put":
        if row['RSI'] <= 40 and row['MACDh'] < -0.3 and ema_diff_ratio < -0.002:
            return "强"
        elif row['RSI'] <= 45 and row['MACDh'] < 0 and ema_diff_ratio < 0:
            return "中"
        elif row['RSI'] > 50 or ema_diff_ratio > 0:
            return "弱"
        else:
            if rsi_slope < -0.1:
                return "中"
            return "弱"

    return "中"

def check_call_entry(row):
    return row['Close'] > row['EMA20'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15

def check_put_entry(row):
    return row['Close'] < row['EMA20'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15

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

# ========== 信号判断主逻辑 ==========
def generate_signal(df):
    if df.empty or 'MACD' not in df.columns or df['MACD'].isnull().all() or len(df) < 6:
        return None, None

    state = load_last_signal()
    pos = state.get("position", "none")
    idx = len(df) - 1
    row = df.iloc[idx]
    prev = df.iloc[idx - 1]
    sideways = is_sideways(row, df, idx)

    # ✅ 新增：持仓状态下，优先检测强烈反转机会
    if pos == "call" and allow_top_rebound_put(row, prev):
        state["position"] = "put"
        save_last_signal(state)
        strength = determine_strength(row, "put")
        return row.name, f"🔁 强势反转 Call → Put（顶部反转 Put 捕捉，{strength}）"

    elif pos == "put" and allow_bottom_rebound_call(row, prev):
        state["position"] = "call"
        save_last_signal(state)
        strength = determine_strength(row, "call")
        return row.name, f"🔁 强势反转 Put → Call（底部反弹 Call 捕捉，{strength}）"

    # 原有出场判断逻辑
    if pos == "call" and check_call_exit(row):
        if is_trend_continuation(row, prev, "call"):
            return row.name, f"⏳ 趋势中继豁免，Call 持仓不出场（RSI={row['RSI']:.1f}, MACDh={row['MACDh']:.3f}）"
        strength = determine_strength(row, "call")
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row) and not sideways:
            state["position"] = "put"
            strength_put = determine_strength(row, "put")
            save_last_signal(state)
            return row.name, f"🔁 反手 Put：Call 出场 + Put 入场（{strength_put}）"
        return row.name, f"⚠️ Call 出场信号（{strength}）"

    elif pos == "put" and check_put_exit(row):
        if is_trend_continuation(row, prev, "put"):
            return row.name, f"⏳ 趋势中继豁免，Put 持仓不出场（RSI={row['RSI']:.1f}, MACDh={row['MACDh']:.3f}）"
        strength = determine_strength(row, "put")
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row) and not sideways:
            state["position"] = "call"
            strength_call = determine_strength(row, "call")
            save_last_signal(state)
            return row.name, f"🔁 反手 Call：Put 出场 + Call 入场（{strength_call}）"
        return row.name, f"⚠️ Put 出场信号（{strength}）"

    elif pos == "none":
        if sideways:
            if allow_bottom_rebound_call(row, prev):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                save_last_signal(state)
                return row.name, f"📈 底部反弹 Call 捕捉（{strength}）"
            elif allow_top_rebound_put(row, prev):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                save_last_signal(state)
                return row.name, f"📉 顶部反转 Put 捕捉（{strength}）"
        else:
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                save_last_signal(state)
                return row.name, f"📈 主升浪 Call 入场（{strength}）"
            elif check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                save_last_signal(state)
                return row.name, f"📉 主跌浪 Put 入场（{strength}）"

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
        print(f"🕒 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        force_clear_at_close()

        state = load_last_signal()
        print(f"📦 当前仓位状态：{state.get('position', 'none')}")
        print("-" * 60)

        if not is_market_open_now():
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 🕗 盘前/盘后，不进行信号判断")
            return

        df = get_data()
        time_signal, signal = generate_signal(df)
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
