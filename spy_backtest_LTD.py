import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 数据获取 =========
def fetch_data(start_date, end_date):
    df = yf.download(SYMBOL, start=start_date, end=end_date + timedelta(days=1), interval="1m", prepost=True, progress=False, auto_adjust=False)
    df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]
    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    bbands = df.ta.bbands(length=20)
    df = pd.concat([df, macd, bbands], axis=1)
    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df["BBU"] = df["BBU_20_2.0"]
    df["BBL"] = df["BBL_20_2.0"]
    df = df.dropna()
    return df

# ========= 工具函数 =========
def calculate_rsi_slope(df, period=5):
    rsi = df["RSI"]
    slope = (rsi - rsi.shift(period)) / period
    return slope

def is_market_day(ts):
    cal = nasdaq.schedule(start_date=ts.date(), end_date=ts.date())
    return not cal.empty

def allow_bottom_rebound_call(row, prev):
    return (
        row['Close'] < row['BBL'] and
        row['RSI'] > prev['RSI'] and
        row['MACDh'] > prev['MACDh'] and
        row['MACD'] > -0.3
    )

def allow_top_rebound_put(row, prev):
    return (
        row['Close'] > row['BBU'] and
        row['RSI'] < prev['RSI'] and
        row['MACDh'] < prev['MACDh'] and
        row['MACD'] < 0.3
    )

def allow_bollinger_rebound(row, prev_row, direction):
    if direction == "CALL":
        return (
            prev_row["Close"] < prev_row["BBL"] and
            row["Close"] > row["BBL"] and
            row["RSI"] > 48 and row["MACD"] > 0
        )
    elif direction == "PUT":
        return (
            prev_row["Close"] > prev_row["BBU"] and
            row["Close"] < row["BBU"] and
            row["RSI"] < 52 and row["MACD"] < 0
        )
    return False

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    last_signal_time = None
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name
        date = ts.date()
        tstr = ts.strftime("%Y-%m-%d %H:%M:%S")
        current_time = ts.time()

        if not is_market_day(ts):
            continue  # 跳过非交易日

        # 盘后强制空仓
        if current_time >= REGULAR_END and in_position is not None:
            signals.append(f"[{tstr}] 🛑 市场收盘，清空仓位")
            in_position = None
            continue

        # 盘前/盘后不处理信号
        if current_time < REGULAR_START or current_time >= REGULAR_END:
            continue

        # 避免重复发信号
        if last_signal_time == row.name:
            continue

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]
        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        # 出场逻辑 + 结构反手
        if in_position == "CALL" and rsi < 50 and slope < 0 and macd < 0:
            signals.append(f"[{tstr}] ⚠️ Call 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name
            if (rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0) or allow_top_rebound_put(row, prev):
                signals.append(f"[{tstr}] 📉 反手 Put：Call 结构破坏 + Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            continue

        elif in_position == "PUT" and rsi > 50 and slope > 0 and macd > 0:
            signals.append(f"[{tstr}] ⚠️ Put 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name
            if (rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0) or allow_bottom_rebound_call(row, prev):
                signals.append(f"[{tstr}] 📈 反手 Call：Put 结构破坏 + Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            continue

        # 入场判断（趋势 + 反弹）
        if in_position is None:
            if rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0:
                signals.append(f"[{tstr}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            elif rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0:
                signals.append(f"[{tstr}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            elif allow_bottom_rebound_call(row, prev) or allow_bollinger_rebound(row, prev, "CALL"):
                signals.append(f"[{tstr}] 📉 底部反弹 Call 捕捉（评分：4/5）")
                in_position = "CALL"
                last_signal_time = row.name
            elif allow_top_rebound_put(row, prev) or allow_bollinger_rebound(row, prev, "PUT"):
                signals.append(f"[{tstr}] 📈 顶部反转 Put 捕捉（评分：3/5）")
                in_position = "PUT"
                last_signal_time = row.name

    return signals

# ========= 回测入口 =========
def backtest():
    today = datetime.now(tz=EST).date()
    start = today - timedelta(days=2)
    end = today
    print(f"[🔁 回测开始] {start} ~ {end}")
    df = fetch_data(start, end)
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()

