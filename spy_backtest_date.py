import os
import pandas as pd
import yfinance as yf
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
def compute_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def compute_rsi(series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(series, fast=5, slow=10, signal=20):
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def compute_kdj(df, length=9, signal=3):
    low_min = df['Low'].rolling(length).min()
    high_max = df['High'].rolling(length).max()
    rsv = (df['Close'] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(alpha=1/signal, adjust=False).mean()
    d = k.ewm(alpha=1/signal, adjust=False).mean()
    return k.fillna(50), d.fillna(50)

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
    df['EMA20'] = compute_ema(df['Close'], 20)
    df['EMA50'] = compute_ema(df['Close'], 50)
    df['EMA200'] = compute_ema(df['Close'], 200)
    df['RSI'] = compute_rsi(df['Close'], 14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['MACD'], df['MACDs'], df['MACDh'] = compute_macd(df['Close'], 5, 10, 20)
    df['K'], df['D'] = compute_kdj(df)
    
    df.dropna(subset=['High','Low','Close','RSI','RSI_SLOPE','MACD','MACDh','EMA20','EMA50','EMA200','K','D'], inplace=True)
    return df

# ==== 趋势判断 ====
def is_trend_up(df, idx): return df['EMA50'].iloc[idx] > df['EMA200'].iloc[idx]
def is_trend_down(df, idx): return df['EMA50'].iloc[idx] < df['EMA200'].iloc[idx]

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
    return row['Close'] > row['EMA20'] and row['RSI'] > 53 and row['MACD']>0 and row['MACDh']>0 and row['RSI_SLOPE']>0.15 and row['K']>row['D']

def check_put_entry(row): 
    return row['Close'] < row['EMA20'] and row['RSI'] < 47 and row['MACD']<0 and row['MACDh']<0 and row['RSI_SLOPE']<-0.15 and row['K']<row['D']

def allow_bottom_rebound_call(row, prev): 
    return row['Close'] < row['EMA20'] and row['RSI']>prev['RSI'] and row['MACDh']>prev['MACDh'] and row['MACD']>-0.3 and row['K']>row['D']

def allow_top_rebound_put(row, prev): 
    return row['Close'] > row['EMA20'] and row['RSI']<prev['RSI'] and row['MACDh']<prev['MACDh'] and row['MACD']<0.3 and row['K']<row['D']

def check_call_exit(row): 
    if row['RSI']<50 and row['RSI_SLOPE']<0 and (row['MACD']<0.05 or row['MACDh']<0.05):
        if row['K']>row['D']: return False
        return True
    return False

def check_put_exit(row): 
    if row['RSI']>50 and row['RSI_SLOPE']>0 and (row['MACD']>-0.05 or row['MACDh']>-0.05):
        if row['K']<row['D']: return False
        return True
    return False

def is_trend_continuation(row, prev, pos): 
    return (row['MACDh']>0 and row['RSI']>45) if pos=="call" else (row['MACDh']<0 and row['RSI']<55) if pos=="put" else False

# ==== 回测主逻辑 ====
def backtest(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str,"%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str,"%Y-%m-%d").date()
    print(f"[🔁 回测时间区间] {start_date} ~ {end_date}")

    df = fetch_data(start_date, end_date)
    print(f"数据条数：{len(df)}")
    position = "none"
    signals = []

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

        # 持仓处理
        if position=="call" and allow_top_rebound_put(row,prev) and row['RSI_SLOPE']<-2 and row['MACDh']<0.1:
            signals.append(f"[{ts}] 🔁 Call -> Put")
            position="put"; continue
        if position=="put" and allow_bottom_rebound_call(row,prev) and row['RSI_SLOPE']>2 and row['MACDh']>-0.1:
            signals.append(f"[{ts}] 🔁 Put -> Call")
            position="call"; continue

        # 出场及反手
        if position=="call" and check_call_exit(row):
            signals.append(f"[{ts}] ⚠️ Call 出场"); position="none"
            if check_put_entry(row) and not is_sideways(row,df,i): 
                signals.append(f"[{ts}] 🔁 空仓 -> Put"); position="put"
            continue
        if position=="put" and check_put_exit(row):
            signals.append(f"[{ts}] ⚠️ Put 出场"); position="none"
            if check_call_entry(row) and not is_sideways(row,df,i): 
                signals.append(f"[{ts}] 🔁 空仓 -> Call"); position="call"
            continue

        # 空仓入场
        if position=="none":
            if is_sideways(row,df,i):
                if allow_bottom_rebound_call(row,prev): signals.append(f"[{ts}] 📈 底部反弹 Call"); position="call"
                elif allow_top_rebound_put(row,prev): signals.append(f"[{ts}] 📉 顶部回落 Put"); position="put"
            else:
                if check_call_entry(row): signals.append(f"[{ts}] 📈 主升浪 Call"); position="call"
                elif check_put_entry(row): signals.append(f"[{ts}] 📉 主跌浪 Put"); position="put"
                elif allow_bottom_rebound_call(row,prev): signals.append(f"[{ts}] 📈 趋势中底部反弹 Call"); position="call"
                elif allow_top_rebound_put(row,prev): signals.append(f"[{ts}] 📉 趋势中顶部回落 Put"); position="put"

    last_ts=df.index[-1]
    if last_ts.time()<REGULAR_END and position!="none": 
        signals.append(f"[{last_ts}] ⏰ 收盘前清仓")
    print(f"总信号数：{len(signals)}")
    for s in signals: print(s)

if __name__=="__main__":
    backtest("2025-09-03","2025-09-03")








