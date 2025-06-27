import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# 配置
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ===== 技术指标函数（镜像主策略） =====
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

def strong_volume(row): return row['Volume'] >= row['Vol_MA5']

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
    return (row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACD'] > 0 and row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and strong_volume(row))

def check_put_entry(row):
    return (row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACD'] < 0 and row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and strong_volume(row))

def allow_bottom_rebound_call(row, prev):
    return (row['Close'] > row['VWAP'] and row['RSI'] > prev['RSI'] and row['MACDh'] > prev['MACDh'] and row['MACD'] > -0.3 and strong_volume(row))

def allow_top_rebound_put(row, prev):
    return (row['Close'] < row['VWAP'] and row['RSI'] < prev['RSI'] and row['MACDh'] < prev['MACDh'] and row['MACD'] < 0.3 and strong_volume(row))

def check_call_exit(row):
    return (row['RSI'] < 50 and row['RSI_SLOPE'] < 0 and (row['MACD'] < 0.05 or row['MACDh'] < 0.05))

def check_put_exit(row):
    return (row['RSI'] > 50 and row['RSI_SLOPE'] > 0 and (row['MACD'] > -0.05 or row['MACDh'] > -0.05))

def allow_call_reentry(row, prev):
    return (prev['Close'] < prev['VWAP'] and row['Close'] > row['VWAP'] and row['RSI'] > 53 and row['MACDh'] > 0.1 and strong_volume(row))

def allow_put_reentry(row, prev):
    return (prev['Close'] > prev['VWAP'] and row['Close'] < row['VWAP'] and row['RSI'] < 47 and row['MACDh'] < 0.05 and strong_volume(row))

# ===== 信号判断主逻辑（镜像） =====
def generate_signal(df_slice, current_pos):
    if len(df_slice) < 2:
        return None, None, current_pos
    row = df_slice.iloc[-1]
    prev_row = df_slice.iloc[-2]
    ts = row.name.strftime("%Y-%m-%d %H:%M:%S")

    if current_pos == "call" and check_call_exit(row):
        strength = determine_strength(row, "call")
        if check_put_entry(row) or allow_top_rebound_put(row, prev_row):
            strength_put = determine_strength(row, "put")
            return ts, f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength_put}）", "put"
        return ts, f"⚠️ Call 出场信号（{strength}）", None

    elif current_pos == "put" and check_put_exit(row):
        strength = determine_strength(row, "put")
        if check_call_entry(row) or allow_bottom_rebound_call(row, prev_row):
            strength_call = determine_strength(row, "call")
            return ts, f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength_call}）", "call"
        return ts, f"⚠️ Put 出场信号（{strength}）", None

    elif current_pos is None:
        if check_call_entry(row):
            strength = determine_strength(row, "call")
            return ts, f"📈 主升浪 Call 入场（{strength}）", "call"
        elif check_put_entry(row):
            strength = determine_strength(row, "put")
            return ts, f"📉 主跌浪 Put 入场（{strength}）", "put"
        elif allow_bottom_rebound_call(row, prev_row):
            strength = determine_strength(row, "call")
            return ts, f"🟢 底部反弹 Call 捕捉（{strength}）", "call"
        elif allow_top_rebound_put(row, prev_row):
            strength = determine_strength(row, "put")
            return ts, f"🔴 顶部反转 Put 捕捉（{strength}）", "put"
        elif allow_call_reentry(row, prev_row):
            strength = determine_strength(row, "call")
            return ts, f"📈 趋势回补 Call 再入场（{strength}）", "call"
        elif allow_put_reentry(row, prev_row):
            strength = determine_strength(row, "put")
            return ts, f"📉 趋势回补 Put 再入场（{strength}）", "put"

    return None, None, current_pos

# ===== 回测入口（支持日期自定义） =====
def backtest_main(start_date="2025-06-20", end_date="2025-06-27"):
    print(f"[🔁 回测区间] {start_date} → {end_date}")
    start_dt = pd.Timestamp(start_date).replace(tzinfo=EST) - timedelta(hours=6)
    end_dt = pd.Timestamp(end_date).replace(tzinfo=EST) + timedelta(hours=6)

    df = yf.download(
        SYMBOL,
        start=start_dt.tz_convert("UTC"),
        end=end_dt.tz_convert("UTC"),
        interval="1m",
        prepost=True,
        progress=False,
        auto_adjust=True
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)

    # 日内VWAP重置
    df["Date"] = df.index.date
    df["Vol_MA5"] = df.groupby("Date")["Volume"].transform(lambda x: x.rolling(5).mean())
    df["RSI"] = compute_rsi(df["Close"])
    df["RSI_SLOPE"] = df["RSI"].diff(3)
    df["VWAP"] = df.groupby("Date").apply(lambda g: (g["Close"] * g["Volume"]).cumsum() / g["Volume"].cumsum()).reset_index(level=0, drop=True)
    df = compute_macd(df)
    df.ffill(inplace=True)
    df.dropna(inplace=True)

    current_pos = None
    for i in range(6, len(df)):
        df_slice = df.iloc[i - 2:i + 1]
        ts, signal, new_pos = generate_signal(df_slice, current_pos)
        if signal:
            print(f"[{ts}] {signal}")
            current_pos = new_pos

# ===== 调用 =====
if __name__ == "__main__":
    backtest_main("2025-06-20", "2025-06-27")

