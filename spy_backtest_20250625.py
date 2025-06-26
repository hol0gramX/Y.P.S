import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
EST = ZoneInfo("America/New_York")  # 夏天是EDT，冬天是EST，自动切换时区
nasdaq = mcal.get_calendar("NASDAQ")

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

def get_data():
    now = get_est_now()
    today = now.date()

    start_search = today - timedelta(days=14)
    trading_days = get_trading_days(start_search, today)
    trading_days = trading_days[trading_days <= pd.Timestamp(today)]
    if len(trading_days) < 3:
        raise ValueError("最近交易日不足3个")
    recent_3_days = trading_days[-3:]

    sessions = []
    for d in recent_3_days:
        o, c = get_market_open_close(d.date())
        early = is_early_close(d.date())
        if o is None or c is None:
            raise ValueError(f"{d.date()}无交易时段")
        sessions.append({'date': d.date(), 'open': o, 'close': c, 'early_close': early})

    start_dt = sessions[0]['open']
    end_dt = sessions[-1]['close']

    # 修正时间格式，去掉微秒，避免unconverted data remains错误
    yf_start = start_dt.tz_convert('UTC').replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
    yf_end = (end_dt + timedelta(seconds=1)).tz_convert('UTC').replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

    print(f"[DEBUG] yf_start: {yf_start}, yf_end: {yf_end}")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=yf_start,
        end=yf_end,
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

    valid_mask = pd.Series(False, index=df.index)
    for sess in sessions:
        open_time = sess['open']
        close_time = sess['close']
        early_close = sess['early_close']

        pre_market_start = open_time - timedelta(hours=5, minutes=30)
        pre_market_end = open_time

        market_start = open_time
        market_end = close_time

        if early_close:
            post_market_start = None
            post_market_end = None
        else:
            post_market_start = close_time
            post_market_end = close_time + timedelta(hours=4)

        mask = (
            ((df.index >= pre_market_start) & (df.index < pre_market_end)) |
            ((df.index >= market_start) & (df.index < market_end))
        )
        if post_market_start and post_market_end:
            mask = mask | ((df.index >= post_market_start) & (df.index < post_market_end))

        valid_mask = valid_mask | mask

    df_filtered = df[valid_mask].copy()

    if len(df_filtered) < 30:
        raise ValueError("数据行数不足，无法计算指标")

    df_filtered['Vol_MA5'] = df_filtered['Volume'].rolling(5).mean()
    df_filtered['RSI'] = compute_rsi(df_filtered['Close'], 14).fillna(50)
    df_filtered['VWAP'] = (df_filtered['Close'] * df_filtered['Volume']).cumsum() / df_filtered['Volume'].cumsum()
    df_filtered = compute_macd(df_filtered)
    df_filtered.ffill(inplace=True)

    return df_filtered.dropna()

# 后面代码保持不变，这里省略
# ... 省略信号生成，发送消息，状态读取等函数 ...

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
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                print(f"[DEBUG] 读取持仓状态: {state}")
                return state
    except Exception as e:
        print(f"[ERROR] 读取状态失败: {e}")
    print("[DEBUG] 状态文件不存在或读取失败，默认无仓位")
    return {"position": "none"}

def save_last_signal(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
        print(f"[DEBUG] 保存持仓状态: {state}")
        with open(STATE_FILE, 'r') as f:
            verify = json.load(f)
        print(f"[DEBUG] 验证保存状态: {verify}")
    except Exception as e:
        print(f"[ERROR] 保存状态失败: {e}")

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
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 无信号")

    except Exception as e:
        print(f"[ERROR] 运行异常: {e}")

if __name__ == "__main__":
    main()

