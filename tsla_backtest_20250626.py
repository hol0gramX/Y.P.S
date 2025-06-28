import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from pytz import timezone  # 替换了 zoneinfo
import pandas_market_calendars as mcal
import json
import requests

# ========= 配置 =========
SYMBOL = "TSLA"  # 你想回测的股票是 TSLA
EST = timezone("America/New_York")  # 使用 pytz 替代 zoneinfo
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)
nasdaq = mcal.get_calendar("NASDAQ")

GIST_ID = "7490de39ccc4e20445ef576832bea34b"  # 你的 Gist ID
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# ========= Gist 状态管理 =========
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

# ========= 数据获取 =========
def fetch_data(start_date, end_date):
    df = yf.download(SYMBOL, start=start_date, end=end_date + timedelta(days=1),
                     interval="1m", prepost=True, progress=False, auto_adjust=False)
    df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]

    # 计算技术指标
    df.ta.rsi(length=14, append=True)  # 计算 RSI
    macd = df.ta.macd(fast=12, slow=26, signal=9)  # 计算 MACD
    bbands = df.ta.bbands(length=20)  # 计算布林带
    df = pd.concat([df, macd, bbands], axis=1)

    # 重命名列
    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df["BBU"] = df["BBU_20_2.0"]
    df["BBL"] = df["BBL_20_2.0"]
    df["VWAP"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()

    # 计算 RSI 的变化率（RSI SLOPE）
    df['RSI_SLOPE'] = df['RSI'].diff(3)  # 计算 3 个周期内的变化

    # 清除空值和不需要的列
    df = df.dropna()
    df = df[df[["VWAP", "MACD", "MACDh", "RSI"]].notna().all(axis=1)]
    return df

# ========= 工具函数 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

def is_market_day(ts):
    cal = nasdaq.schedule(start_date=ts.date(), end_date=ts.date())
    return not cal.empty

# ========= 信号生成 =========
def determine_strength(row, direction):
    vwap_diff_ratio = (row['Close'] - row['VWAP']) / row['VWAP']
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5 and vwap_diff_ratio > 0.005:
            return "强"
        elif row['RSI'] < 55 or vwap_diff_ratio < 0:
            return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5 and vwap_diff_ratio < -0.005:
            return "强"
        elif row['RSI'] > 45 or vwap_diff_ratio > 0:
            return "弱"
    return "中"

def check_call_entry(row):
    return row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0

def check_put_entry(row):
    return row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0

def check_call_exit(row):
    return row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05)

def check_put_exit(row):
    return row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05)

def allow_call_reentry(row, prev):
    return prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACDh'] > 0.1

def allow_put_reentry(row, prev):
    return prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACDh'] < 0.05

# ========= 信号判断主逻辑 =========
def generate_signals(df):
    signals = []
    last_signal_time = None
    in_position = None
    state = load_last_signal_from_gist()
    
    for i in range(5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name
        tstr = ts.strftime("%Y-%m-%d %H:%M:%S")
        current_time = ts.time()

        if not is_market_day(ts):
            continue

        if current_time >= REGULAR_END and in_position is not None:
            signals.append(f"[{tstr}] 🚩 市场收盘，清空仓位")
            in_position = None
            continue

        if current_time < REGULAR_START or current_time >= REGULAR_END:
            continue

        if last_signal_time == row.name:
            continue

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]
        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        # 主要信号判断
        if in_position == "CALL" and check_call_exit(row):
            signals.append(f"[{tstr}] ⚠️ Call 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name
            if check_put_entry(row) or allow_put_reentry(row, prev):
                signals.append(f"[{tstr}] 📉 反手 Put：Call 结构破坏 + Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            continue

        elif in_position == "PUT" and check_put_exit(row):
            signals.append(f"[{tstr}] ⚠️ Put 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name
            if check_call_entry(row) or allow_call_reentry(row, prev):
                signals.append(f"[{tstr}] 📈 反手 Call：Put 结构破坏 + Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            continue

        if in_position is None:
            if check_call_entry(row):
                signals.append(f"[{tstr}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            elif check_put_entry(row):
                signals.append(f"[{tstr}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            elif allow_call_reentry(row, prev):
                signals.append(f"[{tstr}] 📈 趋势回补 Call 再入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            elif allow_put_reentry(row, prev):
                signals.append(f"[{tstr}] 📉 趋势回补 Put 再入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name

    return signals

# ========= 回溯入口 =========
def backtest(start_date_str="2025-06-26", end_date_str="2025-06-27"):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    print(f"[🔁 回溯开始] {start_date} ~ {end_date}")
    df = fetch_data(start_date, end_date)
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

# ========= 执行 =========
if __name__ == "__main__":
    backtest("2025-06-26", "2025-06-27")

