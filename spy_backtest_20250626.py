# ✅ 自动保存信号为 CSV 的回测版本
# 文件名：spy_backtest_20250626.py

import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# -------- 配置 --------
SYMBOL = "SPY"
STATE_FILE = "last_signal.json"
EST = ZoneInfo("America/New_York")
CSV_LOG_NAME = "signal_log_backtest.csv"

# -------- 时间函数 --------
def get_est_now():
    return datetime.now(tz=EST)

# -------- 指标计算 --------
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

# -------- 趋势判断 --------
def get_latest_5min_trend(df_5min, ts):
    try:
        recent = df_5min.loc[(df_5min.index <= ts) & (df_5min.index > ts - timedelta(hours=2))]
        macd = ta.macd(recent['Close'])
        macdh = macd['MACDh_12_26_9'].dropna()
        recent_macdh = macdh.iloc[-5:]
        if (recent_macdh > 0).all():
            return {"trend": "📈上涨"}
        elif (recent_macdh < 0).all():
            return {"trend": "📉下跌"}
        else:
            return {"trend": "🔁震荡"}
    except:
        return None

# -------- 信号判断 --------
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']

def determine_strength(row, direction):
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5: return "强"
        elif row['RSI'] < 55: return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5: return "强"
        elif row['RSI'] > 45: return "弱"
    return "中"

def check_call_entry(row): return row['Close'] > row['VWAP'] and row['RSI'] > 50 and row['MACDh'] > -0.1 and strong_volume(row)
def check_put_entry(row): return row['Close'] < row['VWAP'] and row['RSI'] < 51 and row['MACDh'] < 0.15 and strong_volume(row)
def check_call_exit(row): return row['RSI'] < 48 and strong_volume(row)
def check_put_exit(row): return row['RSI'] > 52 and strong_volume(row)

def load_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# -------- 数据获取 --------
def get_data():
    now = get_est_now()
    end_dt = now.replace(hour=16, minute=0, second=1)
    start_dt = end_dt - timedelta(days=2)
    df = yf.download(SYMBOL, interval="1m", start=start_dt, end=end_dt, progress=False, prepost=True, auto_adjust=True)
    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
    df = df.dropna(subset=['High','Low','Close','Volume'])
    df = df[df['Volume'] > 0]
    df.index = df.index.tz_localize('UTC').tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# -------- 主流程 --------
def main():
    print(f"[🔁 回测开始] {get_est_now().isoformat()}")
    try:
        df = get_data()
        df_5min = yf.download(SYMBOL, interval='5m', period='2d', progress=False, auto_adjust=True)
        df_5min.index = df_5min.index.tz_localize("UTC").tz_convert(EST) if df_5min.index.tz is None else df_5min.index.tz_convert(EST)

        state = load_last_signal()
        signals = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            time_est = row.name
            signal = None

            trend_info = get_latest_5min_trend(df_5min, time_est)
            trend_label = f"{trend_info['trend']}（5min）" if trend_info else "未知"

            if state["position"] == "call" and check_call_exit(row):
                state["position"] = "none"
                if check_put_entry(row):
                    strength = determine_strength(row, "put")
                    state["position"] = "put"
                    signal = f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}，趋势：{trend_label}）"
                else:
                    signal = f"⚠️ Call 出场信号（趋势：{trend_label}）"

            elif state["position"] == "put" and check_put_exit(row):
                state["position"] = "none"
                if check_call_entry(row):
                    strength = determine_strength(row, "call")
                    state["position"] = "call"
                    signal = f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}，趋势：{trend_label}）"
                else:
                    signal = f"⚠️ Put 出场信号（趋势：{trend_label}）"

            elif state["position"] == "none":
                if check_call_entry(row):
                    strength = determine_strength(row, "call")
                    state["position"] = "call"
                    signal = f"📈 主升浪 Call 入场（{strength}，趋势：{trend_label}）"
                elif check_put_entry(row):
                    strength = determine_strength(row, "put")
                    state["position"] = "put"
                    signal = f"📉 主跌浪 Put 入场（{strength}，趋势：{trend_label}）"

            if signal:
                signals.append((time_est, signal))
                save_last_signal(state)

        if signals:
            with open(CSV_LOG_NAME, "w") as f:
                f.write("timestamp,signal\n")
                for ts, msg in signals:
                    f.write(f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{msg}\n")
            print(f"[✅ 保存完成] 写入 {CSV_LOG_NAME} 共 {len(signals)} 条信号")
        else:
            print("[信息] 今日无信号生成")

    except Exception as e:
        print(f"[❌ 回测失败] {e}")

if __name__ == "__main__":
    main()



