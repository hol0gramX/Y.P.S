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
    if macd is None:
        df['MACD'] = df['MACDs'] = df['MACDh'] = 0
    else:
        df['MACD'] = macd['MACD_5_10_20'].fillna(0)
        df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
        df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=length, d=signal, smooth_k=signal)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

# ======== 信号条件拆解 ========
def check_call_entry(row):
    return {
        "Close>EMA20": row['Close'] > row['EMA20'],
        "RSI>53": row['RSI'] > 53,
        "MACD>0": row['MACD'] > 0,
        "MACDh>0": row['MACDh'] > 0,
        "RSI_SLOPE>0.15": row['RSI_SLOPE'] > 0.15,
        "K>D": row['K'] > row['D'],
        "Signal": (row['Close'] > row['EMA20'] and row['RSI'] > 53 and row['MACD'] > 0 and 
                   row['MACDh'] > 0 and row['RSI_SLOPE'] > 0.15 and row['K'] > row['D'])
    }

def check_put_entry(row):
    return {
        "Close<EMA20": row['Close'] < row['EMA20'],
        "RSI<47": row['RSI'] < 47,
        "MACD<0": row['MACD'] < 0,
        "MACDh<0": row['MACDh'] < 0,
        "RSI_SLOPE<-0.15": row['RSI_SLOPE'] < -0.15,
        "K<D": row['K'] < row['D'],
        "Signal": (row['Close'] < row['EMA20'] and row['RSI'] < 47 and row['MACD'] < 0 and 
                   row['MACDh'] < 0 and row['RSI_SLOPE'] < -0.15 and row['K'] < row['D'])
    }

# ======== 主诊断逻辑 ========
def main():
    df = yf.download("SPY", interval="1m", period="1d", prepost=False, auto_adjust=True)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 指标计算
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    df = compute_macd(df)
    df = compute_kdj(df)

    # 截取 9:30–11:40
    df = df.between_time("09:30", "11:40")

    print("="*80)
    print("🕒 诊断区间数据 (9:30–11:40) 前20行")
    print(df[['Close','EMA20','RSI','RSI_SLOPE','MACD','MACDh','K','D']].head(20))

    print("="*80)
    print("📈 逐分钟条件诊断")
    for t, row in df.iterrows():
        call = check_call_entry(row)
        put = check_put_entry(row)
        status = f"{t.strftime('%H:%M')} | "
        if call["Signal"]:
            status += "✅ CALL 信号触发"
        elif put["Signal"]:
            status += "✅ PUT 信号触发"
        else:
            status += "❌ 无信号"
        # 打印每个条件是否满足，方便分析
        status += f" | CALL: {[(k,v) for k,v in call.items() if k!='Signal']}"
        status += f" | PUT: {[(k,v) for k,v in put.items() if k!='Signal']}"
        print(status)

if __name__ == "__main__":
    main()


