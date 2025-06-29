import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========== 配置 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)

DEBUG_MODE = True  # ⬅️ 设置为 True 时，打印 6月27日 09:30 前最后5条数据

# ========== 时间工具 ==========
def is_market_day(dt):
    sched = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    return not sched.empty

# ========== 数据获取 ==========
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
        raise ValueError("❌ 无数据")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df = df[~df.index.duplicated(keep='last')]

    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    df.dropna(subset=['High', 'Low', 'Close', 'Volume', 'Vol_MA5', 'RSI', 'RSI_SLOPE', 'VWAP', 'MACD', 'MACDh'], inplace=True)

    return df

# ========== 回测函数 ==========
def backtest(start_date_str, end_date_str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    print(f"[🔁 回测时间区间] {start_date} ~ {end_date}")
    df = fetch_data(start_date, end_date)
    print(f"✅ 数据条数：{len(df)}")

    # ========== 如果开启 DEBUG 模式 ==========
    if DEBUG_MODE:
        target_day = datetime(2025, 6, 27, 9, 30, tzinfo=EST)
        df_debug = df[df.index < target_day]
        print("\n🔍 [DEBUG] 6月27日09:30前最后5条数据（含指标）:")
        print(df_debug.tail(5)[['Close', 'Volume', 'Vol_MA5', 'RSI', 'RSI_SLOPE', 'MACD', 'MACDh', 'VWAP']])

    # 你可以在此继续插入你的完整回测逻辑（如 position 判断、信号打印等）

if __name__ == "__main__":
    backtest("2025-06-27", "2025-06-27")
