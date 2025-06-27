import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= 配置区域 =========
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========= 工具函数 =========
def fetch_data():
    start = (datetime.now(tz=EST) - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (datetime.now(tz=EST) + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")

    # 修复 MultiIndex 问题
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.tz_convert(EST)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    return df.dropna()

def generate_signals(df):
    signals = []
    in_position = False
    position_type = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]

        rsi = row["RSI_14"]
        macd = row["MACD_12_26_9"]
        macdh = row["MACDh_12_26_9"]
        macds = row["MACDs_12_26_9"]
        close = row["Close"]

        # 计算 RSI 突变斜率
        prev_rsi = prev_row["RSI_14"]
        rsi_slope = rsi - prev_rsi

        timestamp = row.name.strftime("%Y-%m-%d %H:%M:%S")

        # Call 入场
        if not in_position and rsi > 53 and rsi_slope > 1.5 and macd > macds:
            signals.append(f"[{timestamp}] 📈 主升浪 Call 入场（中，趋势：未知）")
            in_position = True
            position_type = "call"
            continue

        # Put 入场
        if not in_position and rsi < 40 and rsi_slope < -1.5 and macd < macds:
            signals.append(f"[{timestamp}] 📉 主跌浪 Put 入场（中，趋势：未知）")
            in_position = True
            position_type = "put"
            continue

        # 出场信号
        if in_position:
            exit_signal = False
            if position_type == "call" and (rsi < 50 or macd < macds):
                exit_signal = True
            elif position_type == "put" and (rsi > 45 or macd > macds):
                exit_signal = True

            if exit_signal:
                signals.append(f"[{timestamp}] ⚠️ {position_type.capitalize()} 出场信号（弱，趋势：未知）")
                in_position = False
                position_type = None

    return signals

def backtest():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)
    log_path = "signal_log_backtest.csv"

    pd.DataFrame({"signal": signals}).to_csv(log_path, index=False)
    print(f"[✅ 保存完成] 写入 {log_path} 共 {len(signals)} 条信号")

if __name__ == "__main__":
    backtest()
