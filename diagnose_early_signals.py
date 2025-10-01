import yfinance as yf
import pandas as pd
import pandas_ta_remake as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

# ====== 技术指标计算函数 ======
def compute_rsi(s, length=14):
    try:
        delta = s.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        rs = up.rolling(length).mean() / down.rolling(length).mean()
        rsi = (100 - 100 / (1 + rs)).fillna(50)
        return rsi
    except Exception as e:
        print("RSI计算失败:", e)
        return None

def compute_macd(df):
    try:
        macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
        df['MACD'] = macd['MACD_5_10_20'].fillna(0)
        df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
        df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
        return df
    except Exception as e:
        print("MACD计算失败:", e)
        return None

def compute_kdj(df):
    try:
        kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3, smooth_k=3)
        df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
        df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
        return df
    except Exception as e:
        print("KDJ计算失败:", e)
        return None

def compute_ema(df):
    try:
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA50'] = ta.ema(df['Close'], length=50)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        return df
    except Exception as e:
        print("EMA计算失败:", e)
        return None

# ====== 主函数 ======
def main():
    print("开始 pre-market 数据诊断 (4:00–11:40)…")
    
    df = yf.download(
        "SPY", interval="1m", period="1d", progress=False, prepost=True, auto_adjust=True
    )
    
    if df.empty:
        print("数据为空，无法计算指标")
        return

    print(f"原始数据行数: {len(df)}")
    
    # 转时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 选取 pre-market + 盘中数据
    df = df.between_time("04:00", "11:40")
    print(f"04:00–11:40 数据行数: {len(df)}")
    
    # 检查NaN数量
    print("\n每列NaN数量：")
    print(df.isna().sum())

    # RSI
    df['RSI'] = compute_rsi(df['Close'])
    print("\nRSI 前10行:")
    print(df['RSI'].head(10))

    # EMA
    df = compute_ema(df)
    for ema in ['EMA20','EMA50','EMA200']:
        print(f"\n{ema} 前10行:")
        print(df[ema].head(10))

    # MACD
    df = compute_macd(df)
    for col in ['MACD','MACDs','MACDh']:
        print(f"\n{col} 前10行:")
        print(df[col].head(10))

    # KDJ
    df = compute_kdj(df)
    for col in ['K','D']:
        print(f"\n{col} 前10行:")
        print(df[col].head(10))

if __name__ == "__main__":
    main()
