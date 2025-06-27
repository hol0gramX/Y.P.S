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
    return not schedule.empty

def fetch_data():
    end = get_est_now()
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m", auto_adjust=True)
    df = df[['Close']].copy()
    df.rename(columns={"Close": "close"}, inplace=True)
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df.ta.sma(length=5, append=True)
    df.ta.sma(length=10, append=True)
    df.ta.sma(length=20, append=True)
    return df

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"position": "flat"}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def slope(series, period=3):
    if len(series) < period:
        return 0
    y = series[-period:]
    x = range(period)
    slope = pd.Series(y).diff().mean()
    return slope

def generate_signals(df):
    signals = []
    state = {"position": "flat"}
    for i in range(20, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        time_str = row.name.strftime("%Y-%m-%d %H:%M:%S")

        rsi = row['RSI_14']
        macd = row['MACD_12_26_9']
        signal = row['MACDs_12_26_9']
        hist = row['MACDh_12_26_9']
        rsi_slope = slope(df['RSI_14'].iloc[i-3:i+1], period=3)

        # 多头信号
        if state['position'] == 'flat':
            if rsi > 53 and rsi_slope > 2 and macd > signal and hist > 0:
                signals.append(f"[{time_str}] 📈 主升浪 Call 入场")
                state['position'] = 'call'

        elif state['position'] == 'call':
            if rsi < 48 or macd < signal:
                signals.append(f"[{time_str}] ⚠️ Call 出场信号")
                state['position'] = 'flat'

        elif state['position'] == 'put':
            if rsi > 52 or macd > signal:
                signals.append(f"[{time_str}] ⚠️ Put 出场信号")
                state['position'] = 'flat'

        # 空头信号
        if state['position'] == 'flat':
            if rsi < 47 and rsi_slope < -2 and macd < signal and hist < 0:
                signals.append(f"[{time_str}] 📉 主跌浪 Put 入场")
                state['position'] = 'put'

    return signals

def backtest():
    now = get_est_now()
    if not is_market_open(now):
        print("[🔒] 市场休市，跳过回测")
        return

    df = fetch_data()
    signals = generate_signals(df)

    print(f"[🔁 回测开始] {now.isoformat()}")
    for signal in signals:
        print(signal)

    with open("signal_log_backtest.csv", "w") as f:
        for signal in signals:
            f.write(signal + "\n")
    print(f"[✅ 保存完成] 写入 signal_log_backtest.csv 共 {len(signals)} 条信号")

if __name__ == "__main__":
    backtest()
