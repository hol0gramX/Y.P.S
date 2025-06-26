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
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df


def get_data():
    df = yf.download(SYMBOL, interval="1m", period="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    if df.empty:
        raise ValueError("无法获取数据")
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'], 14).fillna(50)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
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
        print("数据不足6行，跳过")
        return None, None

    row = df.iloc[-1]
    state = load_last_signal()
    current_pos = state.get("position", "none")

    now_est = datetime.now(ZoneInfo("America/New_York"))
    row_time = row.name
    if row_time.tzinfo is None:
        row_time = row_time.tz_localize("UTC")
    row_time_est = row_time.tz_convert(ZoneInfo("America/New_York"))
    delay_minutes = int((now_est - row_time_est).total_seconds() / 60)

    # Debug 输出
    print(f"\n[Debug] 当前时间：{now_est.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"[Debug] 最新数据时间：{row_time_est.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"[Debug] ⏱ 数据延迟：{delay_minutes} 分钟")
    print(f"[Debug] 当前状态：{current_pos}")
    print(f"[Debug] Close: {row['Close']:.2f}, RSI: {row['RSI']:.2f}, VWAP: {row['VWAP']:.2f}, "
          f"Vol: {row['Volume']:.0f}, Vol_MA5: {row['Vol_MA5']:.0f}")
    print(f"[Debug] MACD: {row['MACD']:.4f}, MACDs: {row['MACDs']:.4f}, MACDh: {row['MACDh']:.4f}")

    if current_pos == "call":
        print("[Debug] 检查 Call 出场条件：RSI < 48 且强成交量")
        if check_call_exit(row):
            print("[Debug] ✅ 满足 Call 出场")
            state["position"] = "none"
            save_last_signal(state)
            if check_put_entry(row):
                strength = determine_strength(row, "put")
                state["position"] = "put"
                save_last_signal(state)
                return row_time_est, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}）"
            return row_time_est, "⚠️ Call 出场信号"

    elif current_pos == "put":
        print("[Debug] 检查 Put 出场条件：RSI > 52 且强成交量")
        if check_put_exit(row):
            print("[Debug] ✅ 满足 Put 出场")
            state["position"] = "none"
            save_last_signal(state)
            if check_call_entry(row):
                strength = determine_strength(row, "call")
                state["position"] = "call"
                save_last_signal(state)
                return row_time_est, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}）"
            return row_time_est, "⚠️ Put 出场信号"

    elif current_pos == "none":
        print("[Debug] 检查是否满足 Call 或 Put 入场条件")
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            print("[Debug] ✅ 满足 Call 入场")
            state["position"] = "call"
            save_last_signal(state)
            return row_time_est, f"📈 主升浪 Call 入场（{strength}）"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            print("[Debug] ✅ 满足 Put 入场")
            state["position"] = "put"
            save_last_signal(state)
            return row_time_est, f"📉 主跌浪 Put 入场（{strength}）"

    print("[Debug] ❌ 无入场/出场信号")
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
    try:
        df = get_data()
        time_signal, signal = generate_signal(df)
        if signal and time_signal:
            msg = f"[{time_signal.strftime('%Y-%m-%d %H:%M:%S %Z')}] {signal}"
            print(msg)
            send_to_discord(msg)
        else:
            print(f"[{get_est_now().strftime('%Y-%m-%d %H:%M:%S %Z')}] 无信号")
    except Exception as e:
        print("运行出错：", e)


if __name__ == "__main__":
    main()

