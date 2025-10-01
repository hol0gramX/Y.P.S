import yfinance as yf
import pandas as pd
import pandas_ta_remake as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

def compute_rsi(s, length=14):
    delta = s.diff()
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

def compute_kdj(df):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3, smooth_k=3)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

def compute_ema(df):
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    return df

def get_data():
    now = datetime.now(tz=EST)
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)

    df = yf.download(
        "SPY",
        interval="1m",
        start=start_time,
        end=now,
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("数据为空")

    # 转 EST
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 只保留当天数据
    df = df.between_time("04:00", "16:00")

    # 计算指标
    df['RSI'] = compute_rsi(df['Close'])
    df = compute_ema(df)
    df = compute_macd(df)
    df = compute_kdj(df)

    # 向前填充，保证开盘就有信号
    df.ffill(inplace=True)

    # 去掉仍然缺少的关键列
    df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20", "K", "D"], inplace=True)

    return df

