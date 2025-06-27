# ========= 配置区域 =========
import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

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
    market_open = schedule.iloc[0]['market_open'].tz_convert(EST)
    market_close = schedule.iloc[0]['market_close'].tz_convert(EST)
    return market_open <= dt <= market_close

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none", "last_signal_time": ""}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ========= 主逻辑 =========
def fetch_data():
    end = get_est_now()
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df.dropna(inplace=True)
    df.ta.rsi(length=14, append=True)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    return df

def detect_signals(df):
    signals = []
    for i in range(35, len(df)):
        ts = df.index[i]
        rsi = df['RSI_14'].iloc[i]
        rsi_slope = df['RSI_14'].iloc[i] - df['RSI_14'].iloc[i-3]
        macd_hist = df['MACDh_12_26_9'].iloc[i]
        macd_hist_prev = df['MACDh_12_26_9'].iloc[i-1]

        price = df['Close'].iloc[i]
        volume = df['Volume'].iloc[i]

        # ========== 多头入场增强判断 ==========
        if rsi > 60 and macd_hist > 0 and macd_hist > macd_hist_prev:
            signals.append((ts, "📈 主升浪 Call 入场（增强RSI+MACD判断）"))
        elif rsi > 50 and rsi_slope > 6 and macd_hist > 0:
            signals.append((ts, "📈 主升浪 Call 启动信号（RSI拔地+MACD背书）"))

        # ========== 空头入场增强判断 ==========
        elif rsi < 40 and macd_hist < 0 and macd_hist < macd_hist_prev:
            signals.append((ts, "📉 主跌浪 Put 入场（增强RSI+MACD判断）"))
        elif rsi < 50 and rsi_slope < -6 and macd_hist < 0:
            signals.append((ts, "📉 主跌浪 Put 启动信号（RSI坠崖+MACD背书）"))

    return signals

def backtest():
    df = fetch_data()
    signals = detect_signals(df)

    log_file = "signal_log_backtest.csv"
    rows = []
    for ts, signal in signals:
        print(f"[{ts}] {signal}")
        rows.append({"time": ts, "signal": signal})
    pd.DataFrame(rows).to_csv(log_file, index=False)
    print(f"[✅ 保存完成] 写入 {log_file} 共 {len(rows)} 条信号")

if __name__ == '__main__':
    print(f"[🔁 回测开始] {get_est_now()}")
    backtest()
