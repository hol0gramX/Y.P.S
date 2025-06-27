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
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 回测日期 =========
BACKTEST_START = "2024-06-20"
BACKTEST_END = "2024-06-27"

PREMARKET_START = time(4, 0)
REGULAR_START = time(9, 30)
REGULAR_END = time(16, 0)

# ========= 数据获取 =========
def fetch_data(start_date, end_date):
    sessions = nasdaq.schedule(start_date=start_date, end_date=end_date)
    if sessions.empty:
        raise ValueError("选定日期范围内无有效交易日")

    # 获取首尾交易时间并转换为 EST 时区
    session_start = sessions.iloc[0]["market_open"]
    session_end = sessions.iloc[-1]["market_close"]

    if session_start.tz is None:
        session_start = session_start.tz_localize("UTC").tz_convert(EST)
    else:
        session_start = session_start.tz_convert(EST)

    if session_end.tz is None:
        session_end = session_end.tz_localize("UTC").tz_convert(EST)
    else:
        session_end = session_end.tz_convert(EST)

    start = session_start - timedelta(hours=6)
    end = session_end + timedelta(hours=6)

    df = yf.download(
        SYMBOL,
        start=start.tz_convert("UTC"),
        end=end.tz_convert("UTC"),
        interval="1m",
        prepost=True,
        progress=False,
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df["RSI"] = df.ta.rsi(length=14)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df["VWAP"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()
    df["Vol_MA5"] = df["Volume"].rolling(5).mean()
    df["RSI_SLOPE"] = df["RSI"].diff(3)
    df = df.dropna()
    return df

# ========= 信号强度判断 =========
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

# ========= 信号生成 =========
def generate_signals(df):
    signals = []
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        ts = row.name.strftime("%Y-%m-%d %H:%M:%S")
        now_time = row.name.time()

        if now_time < PREMARKET_START:
            continue

        if not (REGULAR_START <= now_time <= REGULAR_END):
            continue

        if now_time == REGULAR_START:
            in_position = None

        rsi = row["RSI"]
        slope = row["RSI_SLOPE"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        vol_ok = row['Volume'] >= row['Vol_MA5']

        direction = "call" if in_position != "PUT" else "put"
        strength = determine_strength(row, direction)

        # === Call 出场 + Put 反手 ===
        if in_position == "CALL":
            if rsi < 50 and slope < 0 and (macd < 0.05 or macdh < 0.05):
                signals.append(f"[{ts}] ⚠️ Call 出场信号（{strength}）")
                in_position = None
                # 反手 Put
                if row['Close'] < row['VWAP'] and rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0 and vol_ok:
                    strength_put = determine_strength(row, "put")
                    signals.append(f"[{ts}] 🔁 反手 Put：Call 结构破坏 + Put 入场（{strength_put}）")
                    in_position = "PUT"
                continue

        # === Put 出场 + Call 反手 ===
        if in_position == "PUT":
            if rsi > 50 and slope > 0 and (macd > -0.05 or macdh > -0.05):
                signals.append(f"[{ts}] ⚠️ Put 出场信号（{strength}）")
                in_position = None
                # 反手 Call
                if row['Close'] > row['VWAP'] and rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0 and vol_ok:
                    strength_call = determine_strength(row, "call")
                    signals.append(f"[{ts}] 🔁 反手 Call：Put 结构破坏 + Call 入场（{strength_call}）")
                    in_position = "CALL"
                continue

        # === Call 入场 ===
        if in_position != "CALL":
            if row['Close'] > row['VWAP'] and rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0 and vol_ok:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                continue

        # === Put 入场 ===
        if in_position != "PUT":
            if row['Close'] < row['VWAP'] and rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0 and vol_ok:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                continue

        # === 趋势回补 Call ===
        if in_position is None:
            if row['Close'] > row['VWAP'] and rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0 and vol_ok:
                signals.append(f"[{ts}] 📈 趋势回补 Call 再入场（{strength}）")
                in_position = "CALL"
                continue

        # === 趋势回补 Put ===
        if in_position is None:
            if row['Close'] < row['VWAP'] and rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0 and vol_ok:
                signals.append(f"[{ts}] 📉 趋势回补 Put 再入场（{strength}）")
                in_position = "PUT"
                continue

    return signals

# ========= 回测入口 =========
def backtest():
    print(f"[\U0001f501 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data(BACKTEST_START, BACKTEST_END)
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()
