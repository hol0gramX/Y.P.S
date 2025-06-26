import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

# --------- Gist 相关配置 ---------
GIST_ID = "7490de39ccc4e20445ef576832bea34b"  # 你的 Gist ID
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")  # 你在 GitHub Secret 里设置的 TOKEN_GIST 需要改成 GIST_TOKEN

# --------- 常规变量 ---------
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# --------- 用于读写 Gist 的函数 ---------
def load_last_signal_from_gist():
    if not GIST_TOKEN:
        print("[DEBUG] GIST_TOKEN 未设置，无法读取持仓状态")
        return {"position": "none"}

    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        gist_data = r.json()
        content = gist_data["files"][GIST_FILENAME]["content"]
        state = json.loads(content)
        print(f"[DEBUG] 从 Gist 读取持仓状态: {state}")
        return state
    except Exception as e:
        print(f"[DEBUG] 从 Gist 读取持仓状态失败: {e}")
        return {"position": "none"}

def save_last_signal_to_gist(state):
    if not GIST_TOKEN:
        print("[DEBUG] GIST_TOKEN 未设置，无法保存持仓状态")
        return

    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        # 先获取 gist 当前内容，防止覆盖其他文件（可选）
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        gist_data = r.json()

        # 更新我们文件的内容
        gist_data["files"][GIST_FILENAME]["content"] = json.dumps(state)

        # PATCH 更新 gist
        r2 = requests.patch(url, headers=headers, json={
            "files": {
                GIST_FILENAME: {
                    "content": json.dumps(state)
                }
            }
        })
        r2.raise_for_status()
        print(f"[DEBUG] 成功保存持仓状态到 Gist: {state}")
    except Exception as e:
        print(f"[DEBUG] 保存持仓状态到 Gist 失败: {e}")

# --------- 持仓状态接口改用 Gist ---------
def load_last_signal():
    return load_last_signal_from_gist()

def save_last_signal(state):
    save_last_signal_to_gist(state)

# --------- 下面是你原来的业务逻辑代码 ---------

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
    if sch.empty: return False
    norm = pd.Timestamp.combine(d, time(16,0)).tz_localize(EST)
    return sch.iloc[0]['market_close'].tz_convert(EST) < norm

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
    now = get_est_now()
    today = now.date()
    trade_days = get_trading_days(today - timedelta(days=14), today)
    trade_days = trade_days[trade_days <= pd.Timestamp(today)]
    if len(trade_days) < 3:
        raise ValueError("交易日不足3")
    recent = trade_days[-3:]

    sessions = []
    for d in recent:
        op, cl = get_market_open_close(d.date())
        early = is_early_close(d.date())
        sessions.append((op, cl, early))

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1]
    yf_start = start_dt.tz_convert('UTC')
    yf_end = end_dt.tz_convert('UTC')

    df = yf.download(SYMBOL, interval="1m",
                     start=yf_start, end=yf_end,
                     progress=False, prepost=True, auto_adjust=True)
    if df.empty:
        raise ValueError("下载数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High','Low','Close','Volume'])
    df = df[df['Volume']>0]
    df.index = df.index.tz_localize('UTC').tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)

    mask = pd.Series(False, index=df.index)
    for op,cl,early in sessions:
        pm_start = None if early else cl
        pm_end = None if early else cl + timedelta(hours=4)
        intervals = [
            (op - timedelta(hours=5, minutes=30), op),
            (op, cl)
        ]
        if pm_start:
            intervals.append((pm_start, pm_end))
        for s,e in intervals:
            mask |= (df.index >= s) & (df.index < e)
    df = df[mask]
    if len(df)<30:
        raise ValueError("过滤后数据不足")

    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close']*df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

def strong_volume(row):
    return float(row['Volume']) >= float(row['Vol_MA5'])

def macd_trending_up(row):
    return float(row['MACD']) > float(row['MACDs']) and float(row['MACDh']) > 0

def macd_trending_down(row):
    return float(row['MACD']) < float(row['MACDs']) and float(row['MACDh']) < 0

def determine_strength(row, direction):
    strength = "中"
    if direction == "call":
        if float(row['RSI']) > 65 and float(row['MACDh']) > 0.5:
            strength = "强"
        elif float(row['RSI']) < 55:
            strength = "弱"
    elif direction == "put":
        if float(row['RSI']) < 35 and float(row['MACDh']) < -0.5:
            strength = "强"
        elif float(row['RSI']) > 45:
            strength = "弱"
    return strength

def check_call_entry(row):
    return (
        float(row['Close']) > float(row['VWAP']) and
        float(row['RSI']) > 52 and
        strong_volume(row) and
        macd_trending_up(row)
    )

def check_put_entry(row):
    return (
        float(row['Close']) < float(row['VWAP']) and
        float(row['RSI']) < 48 and
        strong_volume(row) and
        macd_trending_down(row)
    )

def check_call_exit(row):
    return float(row['RSI']) < 48 and strong_volume(row)

def check_put_exit(row):
    return float(row['RSI']) > 52 and strong_volume(row)

def generate_signal(df):
    if len(df) < 6:
        return None, None

    row = df.iloc[-1]
    state = load_last_signal()
    current_pos = state.get("position", "none")

    time_index = row.name
    if time_index.tzinfo is None:
        time_index = time_index.tz_localize("UTC")
    time_index_est = time_index.tz_convert(EST)

    if current_pos == "call" and check_call_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"
        return time_index_est, "⚠️ Call 出场信号"

    elif current_pos == "put" and check_put_exit(row):
        state["position"] = "none"
        save_last_signal(state)
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"
        return time_index_est, "⚠️ Put 出场信号"

    elif current_pos == "none":
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            state["position"] = "call"
            save_last_signal(state)
            return time_index_est, f"📈 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            state["position"] = "put"
            save_last_signal(state)
            return time_index_est, f"📉 主跌浪 Put 入场（{strength}）"

    return None, None

def send_to_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未设置，消息不发送")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("发送 Discord 失败:", e)

def main():
    print(f"[DEBUG] 当前工作目录: {os.getcwd()}")
    state = load_last_signal()
    print(f"[DEBUG] 程序启动时仓位状态: {state.get('position','none')}")
    try:
        df = get_data()
        time_signal, signal = generate_signal(df)
        if signal and time_signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            now = get_est_now()
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 无交易信号")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()



