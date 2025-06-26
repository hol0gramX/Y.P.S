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
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start, end):
    return nasdaq.schedule(start_date=start, end_date=end).index.tz_localize(None)

def get_market_open_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty: return None, None
    return sch.iloc[0]['market_open'].tz_convert(EST), sch.iloc[0]['market_close'].tz_convert(EST)

def is_early_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty: return False
    norm = pd.Timestamp.combine(d, time(16,0)).tz_localize(EST)
    return sch.iloc[0]['market_close'].tz_convert(EST) < norm

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

def get_data():
    now = get_est_now()
    today = now.date()
    trade_days = get_trading_days(today - timedelta(days=14), today)
    trade_days = trade_days[trade_days <= pd.Timestamp(today)]
    print("交易日列表:", trade_days)
    if len(trade_days) < 3:
        raise ValueError("交易日不足3")
    recent = trade_days[-3:]
    print("最近3交易日:", recent)

    sessions = []
    for d in recent:
        op, cl = get_market_open_close(d.date())
        early = is_early_close(d.date())
        print(f"{d.date()} - 开盘: {op}, 收盘: {cl}, 早收盘: {early}")
        sessions.append((op, cl, early))

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1]
    yf_start = start_dt.tz_convert('UTC')
    yf_end = end_dt.tz_convert('UTC')
    print("yf_range UTC:", yf_start, "-", yf_end)

    df = yf.download(SYMBOL, interval="1m",
                     start=yf_start, end=yf_end,
                     progress=False, prepost=True, auto_adjust=True)
    print("下载Raw数据条数:", len(df))

    if df.empty:
        raise ValueError("下载数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High','Low','Close','Volume'])
    df = df[df['Volume']>0]
    df.index = df.index.tz_localize('UTC').tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    print("UTC->EST后数据条数:", len(df))

    mask = pd.Series(False, index=df.index)
    for op,cl,early in sessions:
        pm_start = None if early else cl
        pm_end = None if early else cl + timedelta(hours=4)
        intervals = [
            (op - timedelta(hours=5, minutes=30), op),
            (op, cl)
        ]
        if pm_start:
            intervals.append((pm_start, pm_end))
        for s,e in intervals:
            mask |= (df.index >= s) & (df.index < e)
    df = df[mask]
    print("过滤后条数:", len(df))
    if len(df)<30:
        raise ValueError("过滤后数据不足")

    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close']*df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# --- 后面的信号逻辑保持---

def main():
    try:
        df = get_data()
        print(df.tail(3))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()


