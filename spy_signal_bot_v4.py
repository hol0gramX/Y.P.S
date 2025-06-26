import os
import json
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta

STATE_FILE = "last_signal.json"
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def get_est_now():
    return datetime.now(tz=ZoneInfo("America/New_York"))


def is_market_open():
    now = get_est_now()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def is_premarket():
    now = get_est_now()
    premarket_start = now.replace(hour=4, minute=0, second=0, microsecond=0)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    return premarket_start <= now < market_open


def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    avg_gain = up.rolling(window=length).mean()
    avg_loss = down.rolling(window=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(df):
    macd = ta.macd(df['Close'])
    if macd is None or macd.isna().all().any():
        raise ValueError("MACD计算失败，结果为空或字段缺失")
    df.loc[:, 'MACD'] = macd['MACD_12_26_9'].fillna(0)
    df.loc[:, 'MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df.loc[:, 'MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df


def get_data():
    df = yf.download(SYMBOL, interval="1m", period="2d", progress=False, prepost=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    if df.empty or len(df) < 30:
        raise ValueError("数据不足，无法计算指标")

    now = get_est_now()
    df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    df_filtered = df[df.index.date == now.date()]

    if len(df_filtered) < 30:
        raise ValueError("当日数据不足，跳过运行")

    df_filtered.loc[:, 'Vol_MA5'] = df_filtered['Volume'].rolling(5).mean()
    df_filtered.loc[:, 'RSI'] = compute_rsi(df_filtered['Close'], 14).fillna(50)
    df_filtered.loc[:, 'VWAP'] = (df_filtered['Close'] * df_filtered['Volume']).cumsum() / df_filtered['Volume'].cumsum()
    df_filtered = compute_macd(df_filtered)

    return df_filtered.dropna()


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
    time_index_est = time_index.tz_convert(ZoneInfo("America/New_York"))

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
        print("DISCORD_WEBHOOK_URL 未设置")
        return
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print("发送 Discord 失败：", e)


def main():
    now = get_est_now()

    if is_premarket():
        try:
            df = get_data()
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 盘前数据采集完成，时间范围: {df.index[0]} ~ {df.index[-1]}")
        except Exception as e:
            print("盘前数据采集出错：", e)
        return

    if not is_market_open():
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] ❌ 非交易时间，跳过运行")
        return

    try:
        df = get_data()
        time_signal, signal = generate_signal(df)
        if signal and time_signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] 无信号")
    except Exception as e:
        print("运行出错：", e)


if __name__ == "__main__":
    main()
