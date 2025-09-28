import os
import pandas as pd
import yfinance as yf
import pandas_ta_remake as ta
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
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)  # 新增 ATR
    df = compute_macd(df)
    df = compute_kdj(df)

    df.dropna(subset=['High','Low','Close','RSI','RSI_SLOPE','MACD','MACDh','EMA20','EMA50','EMA200','K','D','ATR'], inplace=True)
    return df

# ==== 趋势判断 ====
def is_trend_up(df, idx): return df['EMA50'].iloc[idx] > df['EMA200'].iloc[idx]
def is_trend_down(df, idx): return df['EMA50'].iloc[idx] < df['EMA200'].iloc[idx]

# ==== 震荡带判断 ====
def is_sideways(row, df, idx, window=10, price_threshold=0.003, ema_threshold=0.01):
    if idx < window:
        return False
    price_near = abs(row['Close'] - row['EMA20']) / row['EMA20'] < price_threshold
    ema_now = row['EMA20']
    ema_past = df.iloc[idx - window]['EMA20']
    ema_flat = abs(ema_now - ema_past) < ema_threshold
    return price_near and ema_flat

# ==== 信号判断（加入 ATR 条件） ====
def check_call_entry(row): 
    return (
        row['Close'] > row['EMA20']
        and row['RSI'] > 53
        and row['MACD'] > 0
        and row['MACDh'] > 0
        and row['RSI_SLOPE'] > 0.15
        and row['K'] > row['D']
        and (row['Close'] - row['EMA20']) > 0.3 * row['ATR']   # 关键过滤
    )

def check_put_entry(row): 
    return (
        row['Close'] < row['EMA20']
        and row['RSI'] < 47
        and row['MACD'] < 0
        and row['MACDh'] < 0
        and row['RSI_SLOPE'] < -0.15
        and row['K'] < row['D']
        and (row['EMA20'] - row['Close']) > 0.3 * row['ATR']   # 关键过滤
    )

def allow_bottom_rebound_call(row, prev): 
    return row['Close'] < row['EMA20'] and row['RSI']>prev['RSI'] and row['MACDh']>prev['MACDh'] and row['MACD']>-0.3 and row['K']>row['D']

def allow_top_rebound_put(row, prev): 
    return row['Close'] > row['EMA20'] and row['RSI']<prev['RSI'] and row['MACDh']<prev['MACDh'] and row['MACD']<0.3 and row['K']<row['D']

def check_call_exit(row): 
    cond1 = row['Close'] < row['EMA20']
    cond2 = row['MACD'] < 0
    cond3 = row['RSI'] < 50
    cond4 = (row['EMA20'] - row['Close']) > 0.2 * row['ATR']   # 新增
    return (cond1 + cond2 + cond3 + cond4) >= 2

def check_put_exit(row): 
    cond1 = row['Close'] > row['EMA20']
    cond2 = row['MACD'] > 0
    cond3 = row['RSI'] > 50
    cond4 = (row['Close'] - row['EMA20']) > 0.2 * row['ATR']   # 新增
    return (cond1 + cond2 + cond3 + cond4) >= 2

# ==== 主循环（信号流） ====
def signal_flow(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str,"%Y-%m-%d").date()
    print(f"[🔁 模拟时间区间] {start_date} ~ {end_date}")

    df = fetch_data(start_date, end_date)
    print(f"数据条数：{len(df)}")
    position = "none"
    signals = []
    last_exit_i = None

    for i in range(1,len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        ts = row.name
        ttime = ts.time()

        if not is_market_day(ts) or ttime < REGULAR_START or ttime >= REGULAR_END:
            if ttime >= time(15,59) and position!="none":
                signals.append(f"[{ts}] ⏰ 收盘前清仓")
                position="none"
            continue

        # 出场
        if position=="call" and check_call_exit(row):
            signals.append(f"[{ts}] ⚠️ Call 出场"); position="none"; last_exit_i = i; continue
        if position=="put" and check_put_exit(row):
            signals.append(f"[{ts}] ⚠️ Put 出场"); position="none"; last_exit_i = i; continue

        # 空仓入场（延迟反手 3 根K）
        if position=="none":
            if last_exit_i and i - last_exit_i < 3:
                continue  # 等待延迟确认
            if is_sideways(row,df,i):
                if allow_bottom_rebound_call(row,prev): signals.append(f"[{ts}] 📈 底部反弹 Call"); position="call"
                elif allow_top_rebound_put(row,prev): signals.append(f"[{ts}] 📉 顶部回落 Put"); position="put"
            else:
                if is_trend_up(df,i):   # 趋势锁方向
                    if check_call_entry(row): signals.append(f"[{ts}] 📈 主升浪 Call"); position="call"
                elif is_trend_down(df,i):
                    if check_put_entry(row): signals.append(f"[{ts}] 📉 主跌浪 Put"); position="put"

    last_ts=df.index[-1]
    if last_ts.time()<REGULAR_END and position!="none": 
        signals.append(f"[{last_ts}] ⏰ 收盘前清仓")
    print(f"总信号数：{len(signals)}")
    for s in signals: print(s)

if __name__=="__main__":
    signal_flow("2025-09-25","2025-09-26")







