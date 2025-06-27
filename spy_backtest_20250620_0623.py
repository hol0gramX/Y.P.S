import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= 配置 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
PREMARKET_START = datetime.strptime("04:00:00", "%H:%M:%S").time()
REGULAR_START = datetime.strptime("09:30:00", "%H:%M:%S").time()
MARKET_END = datetime.strptime("16:00:00", "%H:%M:%S").time()

# ========= 数据获取 =========
def fetch_data():
    end = datetime.now(tz=EST)
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", prepost=True)
    df.columns = df.columns.get_level_values(0)
    df.index.name = "Datetime"
    if not df.index.tz:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    df = df[~df.index.duplicated(keep='last')]

    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    df["RSI"] = df["RSI_14"]
    df["MACD"] = df["MACD_12_26_9"]
    df["MACDh"] = df["MACDh_12_26_9"]
    df["MACDs"] = df["MACDs_12_26_9"]
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
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

        # 🕓 04:00 前不做任何判断
        if now_time < PREMARKET_START:
            continue

        # ⛔️ 非盘中（盘前/盘后）仅采集数据，不做信号判断
        if not (REGULAR_START <= now_time <= MARKET_END):
            continue

        # 🕘 每天开盘第一根K线默认清空仓位
        if now_time == REGULAR_START:
            in_position = None

        rsi = row["RSI"]
        slope = row["RSI_SLOPE"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        vol_ok = row['Volume'] >= row['Vol_MA5']

        direction = "call" if in_position != "PUT" else "put"
        strength = determine_strength(row, direction)

        # === Call 出场 ===
        if in_position == "CALL":
            if rsi < 50 and slope < 0 and (macd < 0.05 or macdh < 0.05):
                signals.append(f"[{ts}] ⚠️ Call 出场信号（{strength}）")
                in_position = None
                continue

        # === Put 出场 ===
        if in_position == "PUT":
            if rsi > 50 and slope > 0 and (macd > -0.05 or macdh > -0.05):
                signals.append(f"[{ts}] ⚠️ Put 出场信号（{strength}）")
                in_position = None
                continue

        # === Call 入场 ===
        if in_position != "CALL":
            allow_call = (
                row['Close'] > row['VWAP'] and
                rsi > 53 and slope > 0.15 and
                macd > 0 and macdh > 0 and
                vol_ok
            )
            if allow_call:
                signals.append(f"[{ts}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                continue

        # === Put 入场 ===
        if in_position != "PUT":
            allow_put = (
                row['Close'] < row['VWAP'] and
                rsi < 47 and slope < -0.15 and
                macd < 0 and macdh < 0 and
                vol_ok
            )
            if allow_put:
                signals.append(f"[{ts}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                continue

        # === ✅ 趋势回补 Call ===
        if in_position is None:
            allow_call = (
                row['Close'] > row['VWAP'] and
                rsi > 53 and slope > 0.15 and
                macd > 0 and macdh > 0 and
                vol_ok
            )
            if allow_call:
                signals.append(f"[{ts}] 📈 趋势回补 Call 再入场（{strength}）")
                in_position = "CALL"
                continue

        # === ✅ 趋势回补 Put ===
        if in_position is None:
            allow_put = (
                row['Close'] < row['VWAP'] and
                rsi < 47 and slope < -0.15 and
                macd < 0 and macdh < 0 and
                vol_ok
            )
            if allow_put:
                signals.append(f"[{ts}] 📉 趋势回补 Put 再入场（{strength}）")
                in_position = "PUT"
                continue

    return signals

# ========= 回测入口 =========
def backtest():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)
    for sig in signals:
        print(sig)

if __name__ == "__main__":
    backtest()
