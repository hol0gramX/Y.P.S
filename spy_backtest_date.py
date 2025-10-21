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
    df['MA5'] = ta.sma(df['Close'], length=5)
    df['MA10'] = ta.sma(df['Close'], length=10)
    df['MA20'] = ta.sma(df['Close'], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)
    df.dropna(inplace=True)
    return df

# ==== 均线顺序震荡判断 ====
def is_sideways(row, df, idx, window=5, slope_th=0.0006):
    """
    极严格横盘判断（只保留两个条件）：
    1️⃣ MA5, MA10, MA20 顺序混乱
    2️⃣ MA20 斜率过平
    只有同时满足才判定为横盘
    """
    if idx < max(window, 20):
        return False

    # 计算均线
    ma5 = df['Close'].iloc[idx-5:idx].mean()
    ma10 = df['Close'].iloc[idx-10:idx].mean()
    ma20_series = df['Close'].iloc[idx-20:idx]
    ma20 = ma20_series.mean()

    # 1️⃣ 均线顺序判断
    ordered_up = ma5 > ma10 > ma20
    ordered_down = ma5 < ma10 < ma20
    is_messy = not (ordered_up or ordered_down)

    # 2️⃣ MA20 斜率
    y = ma20_series.values
    slope = (y[-1] - y[0]) / len(y) / y[-1]
    is_flat = abs(slope) < slope_th

    # 同时满足两个条件才判横盘
    return is_messy and is_flat


# ==== 信号判断 ====
def check_call_entry(row): 
    return row['Close'] > row['EMA20'] and row['RSI'] > 53 and row['MACD']>0 and row['MACDh']>0 and row['RSI_SLOPE']>0.15 and row['K']>row['D']

def check_put_entry(row): 
    return row['Close'] < row['EMA20'] and row['RSI'] < 47 and row['MACD']<0 and row['MACDh']<0 and row['RSI_SLOPE']<-0.15 and row['K']<row['D']

def check_call_exit(row): 
    if row['RSI']<50 and row['RSI_SLOPE']<0 and (row['MACD']<0.05 or row['MACDh']<0.05):
        if row['K']>row['D']:
            return False
        return True
    return False

def check_put_exit(row): 
    if row['RSI']>50 and row['RSI_SLOPE']>0 and (row['MACD']>-0.05 or row['MACDh']>-0.05):
        if row['K']<row['D']:
            return False
        return True
    return False

def is_trend_continuation(row, prev, pos): 
    return (row['MACDh']>0 and row['RSI']>45) if pos=="call" else (row['MACDh']<0 and row['RSI']<55) if pos=="put" else False

# ==== 回测主逻辑 ====
def backtest(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    print(f"[🔁 回测时间区间] {start_date} ~ {end_date}")

    df = fetch_data(start_date, end_date)
    print(f"数据条数：{len(df)}")
    position = "none"
    signals = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name
        ttime = ts.time()

        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            if ttime >= time(15, 59) and position != "none":
                signals.append(f"[{ts}] ⏰ 收盘前清仓")
                position = "none"
            continue

        # 出场逻辑
        if position=="call" and check_call_exit(row):
            if is_trend_continuation(row, prev, "call"): continue
            signals.append(f"[{ts}] ⚠️ Call 出场"); position="none"
            if check_put_entry(row) and not is_sideways(row,df,i):
                signals.append(f"[{ts}] 🔁 空仓 -> Put"); position="put"
            continue

        if position=="put" and check_put_exit(row):
            if is_trend_continuation(row, prev, "put"): continue
            signals.append(f"[{ts}] ⚠️ Put 出场"); position="none"
            if check_call_entry(row) and not is_sideways(row,df,i):
                signals.append(f"[{ts}] 🔁 空仓 -> Call"); position="call"
            continue

        # 空仓入场逻辑
        if position=="none" and not is_sideways(row,df,i):
            if check_call_entry(row): signals.append(f"[{ts}] 📈 主升浪 Call"); position="call"
            elif check_put_entry(row): signals.append(f"[{ts}] 📉 主跌浪 Put"); position="put"

    last_ts = df.index[-1]
    if last_ts.time() < REGULAR_END and position!="none": 
        signals.append(f"[{last_ts}] ⏰ 收盘前清仓")
    print(f"总信号数：{len(signals)}")
    for s in signals: print(s)

if __name__ == "__main__":
    backtest("2025-10-10", "2025-10-14")






