import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========= 配置区域 =========
STATE_FILE = os.path.abspath("last_signal.json")
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 工具函数 =========
def get_est_now():
    return datetime.now(tz=EST)

def is_market_open(dt):
    schedule = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    if schedule.empty:
        return False
    market_open = schedule.iloc[0]["market_open"].tz_convert(EST)
    market_close = schedule.iloc[0]["market_close"].tz_convert(EST)
    return market_open <= dt <= market_close

def fetch_data():
    end = get_est_now()
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df.dropna(inplace=True)
    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"])
    df["MACD"] = macd["MACD_12_26_9"]
    df["MACDh"] = macd["MACDh_12_26_9"]
    df["MACDs"] = macd["MACDs_12_26_9"]
    return df

# ========= 信号生成逻辑 =========
def generate_signals(df):
    signals = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        time = row.name.to_pydatetime()

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        close = row["Close"]

        # 示例逻辑：仅当 RSI > 53 且 MACDh 正增长时给出 Call 信号
        if rsi is not None and macdh is not None and not pd.isna(rsi) and not pd.isna(macdh):
            if rsi > 53 and macdh > prev["MACDh"]:
                signals.append((time, "📈 主升浪 Call 入场（趋势：增强）"))

    return signals

# ========= 回测主逻辑 =========
def backtest():
    print(f"[🔁 回测开始] {get_est_now().isoformat()}")
    df = fetch_data()
    signals = generate_signals(df)

    log_file = "signal_log_backtest.csv"
    with open(log_file, "w") as f:
        f.write("timestamp,message\n")
        for t, msg in signals:
            f.write(f"{t},{msg}\n")
    print(f"[✅ 保存完成] 写入 {log_file} 共 {len(signals)} 条信号")

if __name__ == "__main__":
    backtest()
