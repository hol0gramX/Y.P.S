import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========= 配置区域 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
STATE_FILE = "last_signal.json"
OUTPUT_FILE = "signal_log_backtest.csv"

# ========= 数据获取 =========
def fetch_data():
    start = (datetime.now(tz=EST) - timedelta(days=2)).strftime("%Y-%m-%d")
    end = (datetime.now(tz=EST) + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", auto_adjust=False)

    # 转换时区
    if not df.index.tz:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)

    # 扁平化列名，防止 pandas-ta 错误
    df.columns = [str(col) for col in df.columns]

    # 添加技术指标
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df["RSI_slope"] = df["RSI_14"].diff()

    return df

# ========= 信号判断主逻辑 =========
def generate_signals(df):
    signals = []
    position = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        timestamp = row.name.strftime("%Y-%m-%d %H:%M:%S")

        rsi = row["RSI_14"]
        macd = row["MACD_12_26_9"]
        macdh = row["MACDh_12_26_9"]
        slope = row["RSI_slope"]

        # ---- 斜率突变逻辑 ----
        slope_rising = slope > 0.5 and prev["RSI_slope"] <= 0.2

        # ---- 入场逻辑 ----
        if position is None:
            if rsi > 53 and macd > 0 and macdh > 0 and slope_rising:
                signals.append(f"[{timestamp}] 📈 主升浪 Call 入场（斜率突变，趋势确认）")
                position = "CALL"
            elif rsi < 40 and macd < 0 and macdh < 0:
                signals.append(f"[{timestamp}] 📉 主跌浪 Put 入场（趋势确认）")
                position = "PUT"

        # ---- 出场逻辑 ----
        elif position == "CALL":
            if rsi < 50 or macdh < 0:
                signals.append(f"[{timestamp}] ⚠️ Call 出场信号")
                position = None
        elif position == "PUT":
            if rsi > 45 or macdh > 0:
                signals.append(f"[{timestamp}] ⚠️ Put 出场信号")
                position = None

    return signals

# ========= 回测函数 =========
def backtest():
    print(f"[🔁 回测开始] {datetime.now(tz=EST)}")
    df = fetch_data()
    signals = generate_signals(df)

    for s in signals:
        print(s)

    # 保存为 CSV
    df_signals = pd.DataFrame(signals, columns=["signal"])
    df_signals.to_csv(OUTPUT_FILE, index=False)
    print(f"[✅ 保存完成] 写入 {OUTPUT_FILE} 共 {len(signals)} 条信号")

# ========= 执行 =========
if __name__ == "__main__":
