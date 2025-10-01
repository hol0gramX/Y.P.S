import pandas as pd
import yfinance as yf
import pandas_ta_remake as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

# ====== 技术指标函数 ======
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def compute_ema(df):
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['EMA200'] = ta.ema(df['Close'], length=200)
    return df

def compute_kdj(df):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3, smooth_k=3)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

# ====== 主函数 ======
def main():
    print("开始逐分钟指标健康检查…")
    df = yf.download("SPY", interval="1m", period="1d", prepost=True, auto_adjust=True)
    
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 计算指标
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df = compute_ema(df)
    df = compute_macd(df)
    df = compute_kdj(df)

    # 检查每分钟指标是否异常
    check_cols = ['RSI','RSI_SLOPE','EMA20','EMA50','EMA200','MACD','MACDh','K','D']
    print(f"\n{'时间':<16} " + " ".join([f"{c:<10}" for c in check_cols]))
    for t, row in df.iterrows():
        status = []
        for c in check_cols:
            if pd.isna(row[c]):
                status.append("❌")
            else:
                status.append("✅")
        print(f"{t.strftime('%H:%M'):<16} " + " ".join(status))

if __name__ == "__main__":
    main()

