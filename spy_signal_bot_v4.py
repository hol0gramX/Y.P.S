import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

STATE_FILE = "last_signal.json"
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========== 时间与市场日历处理 ==========
def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start_date, end_date):
    schedule = nasdaq.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.tz_localize(None)

def get_prev_trading_day(date):
    date = pd.Timestamp(date).normalize()
    trading_days = get_trading_days(date - timedelta(days=7), date)
    prev_days = trading_days[trading_days < date]
    if len(prev_days) == 0:
        raise ValueError("未找到之前的交易日")
    return prev_days[-1].date()

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

# ========== 技术指标计算 ==========
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

# ========== 核心数据处理 ==========
def get_data():
    now = get_est_now()
    today = now.date()
    prev_day = get_prev_trading_day(today)

    prev_open, prev_close = get_market_open_close(prev_day)
    today_open, today_close = get_market_open_close(today)

    if prev_close is None or today_open is None:
        raise ValueError("无法获取市场开收盘时间，可能是非交易日")

    # 判断前一个交易日是否early close
    if is_early_close(prev_day):
        # Early close当日无post-market，跳过post-market筛选
        post_market_start = None
        post_market_end = None
    else:
        # 正常收盘日，post-market为收盘后4小时
        post_market_start = prev_close
        post_market_end = prev_close + timedelta(hours=4)

    # pre-market开始时间 = 今日开盘时间 - 5.5小时（一般为4:00AM）
    pre_market_start = today_open - timedelta(hours=5, minutes=30)
    pre_market_end = today_open

    market_start = today_open
    market_end = today_close

    # 下载3天数据，含pre和post
    df = yf.download(
        SYMBOL,
        interval="1m",
        period="3d",
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 筛选数据，post_market_start为None时不筛选post-market时间段
    df_filtered = df[
        (
            (post_market_start is not None) and
            (df.index >= post_market_start) & (df.index < post_market_end)
        ) |
        ((df.index >= pre_market_start) & (df.index < pre_market_end)) |
        ((df.index >= market_start) & (df.index < market_end))
    ].copy()

    if len(df_filtered) < 30:
        raise ValueError("数据行数不足，无法计算指标")

    df_filtered['Vol_MA5'] = df_filtered['Volume'].rolling(5).mean()
    df_filtered['RSI'] = compute_rsi(df_filtered['Close'], 14).fillna(50)
    df_filtered['VWAP'] = (df_filtered['Close'] * df_filtered['Volume']).cumsum() / df_filtered['Volume'].cumsum()
    df_filtered = compute_macd(df_filtered)
    df_filtered.ffill(inplace=True)

    return df_filtered.dropna()

# ========== 策略逻辑（保持原样） ==========
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

def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

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
    now = get_est_now()
    try:
        df = get_data()

        if time(4,0) <= now.time() < time(9,30):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 📊 盘前数据采集完成，时间范围: {df.index[0]} ~ {df.index[-1]}")
            return
        if time(16,0) <= now.time() < time(20,0):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 📊 盘后数据采集完成，时间范围: {df.index[0]} ~ {df.index[-1]}")
            return
        if now.time() >= time(20,0) or now.time() < time(4,0):
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 🌙 非交易时间，跳过运行")
            return

        time_signal, signal = generate_signal(df)
        if signal and time_signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 无交易信号")
    except Exception as e:
        print("运行出错：", e)

if __name__ == "__main__":
    main()


