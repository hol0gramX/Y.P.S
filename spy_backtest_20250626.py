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

def get_market_open_close(dt):
    schedule = nasdaq.schedule(start_date=dt.date(), end_date=dt.date())
    if schedule.empty:
        return None, None
    market_open = schedule.iloc[0]['market_open'].tz_convert(EST)
    market_close = schedule.iloc[0]['market_close'].tz_convert(EST)
    return market_open, market_close

def fetch_data():
    end = get_est_now()
    start = end - timedelta(days=2)
    df = yf.download(SYMBOL, start=start, end=end, interval="1m")
    df = df.copy()  # 防止 SettingWithCopyWarning
    df.index = df.index.tz_convert(EST)
    df.ta.rsi(length=14, append=True)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['RSI_Slope'] = df['RSI_14'].diff()
    return df

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"position": "none"}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def generate_signals(df):
    state = {"position": "none"}
    signals = []
    for i in range(2, len(df)):
        row = df.iloc[i]
        rsi = row['RSI_14']
        rsi_slope = row['RSI_Slope']
        macd = row['MACD_12_26_9']
        macdh = row['MACDh_12_26_9']
        signal = None

        if state['position'] == 'none':
            if rsi > 53 and rsi_slope > 0.15 and macd > 0 and macdh > 0:
                signal = "📈 主升浪 Call 入场（斜率确认）"
                state['position'] = 'call'
            elif rsi < 47 and rsi_slope < -0.15 and macd < 0 and macdh < 0:
                signal = "📉 主跌浪 Put 入场（斜率确认）"
                state['position'] = 'put'
        elif state['position'] == 'call':
            if rsi < 50:
                signal = "⚠️ Call 出场信号"
                state['position'] = 'none'
        elif state['position'] == 'put':
            if rsi > 50:
                signal = "⚠️ Put 出场信号"
                state['position'] = 'none'

        if signal:
            signals.append((df.index[i], signal))
    return signals

def backtest():
    print(f"[🔁 回测开始] {get_est_now().isoformat()}")
    df = fetch_data()
    signals = generate_signals(df)
    for timestamp, signal in signals:
        print(f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {signal}")

if __name__ == "__main__":
    backtest()
