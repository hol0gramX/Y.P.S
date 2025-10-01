import pandas as pd
import yfinance as yf
import pandas_ta_remake as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

# ======== 技术指标函数 ========
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=length, d=signal, smooth_k=signal)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

# ======== 信号条件 ========
def check_call_entry(row):
    return (row['Close'] > row['EMA20'] and row['RSI'] > 53 and row['MACD'] > 0 and 
            row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and row['K'] > row['D'])

def check_put_entry(row):
    return (row['Close'] < row['EMA20'] and row['RSI'] < 47 and row['MACD'] < 0 and 
            row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and row['K'] < row['D'])

# ======== 主诊断逻辑 ========
def main():
    now = datetime.now(tz=EST)
    df = yf.download("SPY", interval="1m", period="1d", prepost=False, auto_adjust=True)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    df = compute_macd(df)
    df = compute_kdj(df)

    # 只截取 9:30–11:40
    df = df.between_time("09:30", "11:40")

    print("="*80)
    print("🕒 诊断区间数据 (9:30–11:40)")
    print(df[['Close','EMA20','RSI','RSI_SLOPE','MACD','MACDh','K','D']].head(20))  # 前20行看看

    print("="*80)
    print("📈 检查逐分钟信号触发情况")
    for t, row in df.iterrows():
        call_ok = check_call_entry(row)
        put_ok = check_put_entry(row)
        if call_ok or put_ok:
            print(f"{t.strftime('%H:%M')} ✅ 信号触发: {'CALL' if call_ok else 'PUT'}")
        else:
            print(f"{t.strftime('%H:%M')} ❌ 无信号")

if __name__ == "__main__":
    main()


