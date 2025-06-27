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

def fetch_data():
    start = (datetime.now(tz=EST) - timedelta(days=2)).date().strftime("%Y-%m-%d")
    end = datetime.now(tz=EST).date().strftime("%Y-%m-%d")
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df.index = df.index.tz_convert(EST)  # 修正时区处理

    # 添加指标
    df.ta.rsi(length=14, append=True)
    macd = df.ta.macd(append=True)
    if macd is None:
        raise ValueError("MACD计算失败")

    df.dropna(inplace=True)
    return df

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": "none"}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def generate_signals(df):
    signals = []
    state = {"position": "none"}
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        time = row.name.strftime("%Y-%m-%d %H:%M:%S")

        rsi = row["RSI_14"]
        macd = row["MACD_12_26_9"]
        macdh = row["MACDh_12_26_9"]

        if state["position"] == "none":
            if rsi > 53 and macd > 0 and macdh > 0:
                signals.append(f"[{time}] 📈 主升浪 Call 入场（趋势：未知）")
                state["position"] = "call"
            elif rsi < 47 and macd < 0 and macdh < 0:
                signals.append(f"[{time}] 📉 主跌浪 Put 入场（趋势：未知）")
                state["position"] = "put"

        elif state["position"] == "call":
            if rsi < 50:
                signals.append(f"[{time}] ⚠️ Call 出场信号（趋势：未知）")
                state["position"] = "none"

        elif state["position"] == "put":
            if rsi > 50:
                signals.append(f"[{time}] ⚠️ Put 出场信号（趋势：未知）")
                state["position"] = "none"

    return signals

def backtest():
    print("[🔁 回测开始]", datetime.now(tz=EST))
    df = fetch_data()
    signals = generate_signals(df)
    output_file = "signal_log_backtest.csv"
    pd.DataFrame({"signal": signals}).to_csv(output_file, index=False)
    print(f"[✅ 保存完成] 写入 {output_file} 共 {len(signals)} 条信号")

if __name__ == "__main__":
    backtest()

