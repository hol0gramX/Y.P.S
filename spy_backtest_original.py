import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ==== 配置 ====
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)

# ==== 时间工具 ====
def is_market_day(dt):
    sched = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not sched.empty

# ==== 技术指标 ====
def compute_rsi(series, length=14):
    delta = series.diff()
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

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=length, d=signal, smooth_k=signal)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

# ==== 数据拉取 ====
def fetch_data(start_date, end_date):
    df = yf.download(
        SYMBOL,
        start=start_date,
        end=end_date + timedelta(days=1),
        interval="1m",
        prepost=True,
        progress=False,
        auto_adjust=True,
    )
    if df.empty:
        raise ValueError("无数据")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]

    # 指标计算
    df['RSI'] = compute_rsi(df['Close'], length=14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)

    df.dropna(subset=['High','Low','Close','RSI','RSI_SLOPE','MACD','MACDh','EMA20','K','D'], inplace=True)
    return df

# ==== 震荡带判断 ====
def is_sideways(row, df, idx, window=3, price_threshold=0.002, ema_threshold=0.02):
    if idx < window:
        return False
    price_near = abs(row['Close'] - row['EMA20']) / row['EMA20'] < price_threshold
    ema_now = row['EMA20']
    ema_past = df.iloc[idx - window]['EMA20']
    ema_flat = abs(ema_now - ema_past) < ema_threshold
    return price_near and ema_flat

# ==== 信号判断 ====
def check_call_entry(row): 
    return (row['Close'] > row['EMA20'] and 
            row['RSI'] > 53 and 
            row['MACD'] > 0 and 
            row['MACDh'] > 0 and 
            row['RSI_SLOPE'] > 0.15 and 
            row['K'] > row['D'])

def check_put_entry(row): 
    return (row['Close'] < row['EMA20'] and 
            row['RSI'] < 47 and 
            row['MACD'] < 0 and 
            row['MACDh'] < 0 and 
            row['RSI_SLOPE'] < -0.15 and 
            row['K'] < row['D'])

# ==== 出场逻辑 ====
def check_call_exit(row, prev):
    prev_macdh = prev['MACDh'] if prev['MACDh'] != 0 else 1e-6  # 防止除以零
    if (row['RSI_SLOPE'] < -0.3 or row['MACDh'] < prev_macdh * 0.5) and row['RSI'] < 55:
        if row['K'] > row['D'] + 2:  
            return False
        return True
    return False

def check_put_exit(row, prev):
    prev_macdh = prev['MACDh'] if prev['MACDh'] != 0 else 1e-6
    if (row['RSI_SLOPE'] > 0.3 or row['MACDh'] > prev_macdh * 0.5) and row['RSI'] > 45:
        if row['K'] < row['D'] - 2:
            return False
        return True
    return False

def is_trend_continuation(row, prev, pos): 
    if pos == "call":
        return (row['MACDh'] > 0 and row['RSI'] > 45)
    elif pos == "put":
        return (row['MACDh'] < 0 and row['RSI'] < 55)
    return False

# ==== 回测主逻辑 ====
def backtest(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str,"%Y-%m-%d").date()
    print(f"[🔁 回测时间区间] {start_date} ~ {end_date}")

    df = fetch_data(start_date, end_date)
    print(f"数据条数：{len(df)}")
    position = "none"
    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        ts = row.name
        ttime = ts.time()

        # ====== 正常回测逻辑 ======
        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            if ttime >= time(15,59) and position != "none":
                signals.append(f"[{ts}] ⏰ 收盘前清仓")
                position = "none"
            continue

        # 出场及反手
        if position == "call" and check_call_exit(row, prev):
            if is_trend_continuation(row, prev, "call"):
                continue
            signals.append(f"[{ts}] ⚠️ Call 出场"); position = "none"
            if check_put_entry(row) and not is_sideways(row, df, i):
                signals.append(f"[{ts}] 🔁 空仓 -> Put"); position = "put"
            continue

        if position == "put" and check_put_exit(row, prev):
            if is_trend_continuation(row, prev, "put"):
                continue
            signals.append(f"[{ts}] ⚠️ Put 出场"); position = "none"
            if check_call_entry(row) and not is_sideways(row, df, i):
                signals.append(f"[{ts}] 🔁 空仓 -> Call"); position = "call"
            continue

        # 空仓入场
        if position == "none":
            if not is_sideways(row, df, i):
                if check_call_entry(row):
                    signals.append(f"[{ts}] 📈 主升浪 Call"); position = "call"
                elif check_put_entry(row):
                    signals.append(f"[{ts}] 📉 主跌浪 Put"); position = "put"

    last_ts = df.index[-1]
    if last_ts.time() < REGULAR_END and position != "none": 
        signals.append(f"[{last_ts}] ⏰ 收盘前清仓")
    print(f"总信号数：{len(signals)}")
    for s in signals:
        print(s)

if __name__=="__main__":
    backtest("2025-10-16","2025-10-16")




