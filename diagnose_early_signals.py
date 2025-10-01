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
    print("开始指标健康检查 (9:30–11:40)…")
    df = yf.download("SPY", interval="1m", period="1d", progress=False)
    if df.empty:
        print("数据为空，无法计算指标")
        return

    # 转时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 截取 9:30–11:40
    df = df.between_time("09:30", "11:40")

    status = {}

    # RSI
    try:
        df['RSI'] = compute_rsi(df['Close'])
        if df['RSI'] is not None:
            status['RSI'] = "OK"
            print("\nRSI 前5行:\n", df['RSI'].head())
        else:
            status['RSI'] = "错误"
    except Exception as e:
        print("RSI处理失败:", e)
        status['RSI'] = "错误"

    # RSI_SLOPE
    try:
        df['RSI_SLOPE'] = df['RSI'].diff(3)
        status['RSI_SLOPE'] = "OK"
        print("\nRSI_SLOPE 前5行:\n", df['RSI_SLOPE'].head())
    except Exception as e:
        print("RSI_SLOPE计算失败:", e)
        status['RSI_SLOPE'] = "错误"

    # EMA
    try:
        df = compute_ema(df)
        for ema in ['EMA20','EMA50','EMA200']:
            if df is not None and ema in df.columns:
                status[ema] = "OK"
                print(f"\n{ema} 前5行:\n", df[ema].head())
            else:
                status[ema] = "错误"
    except Exception as e:
        print("EMA处理失败:", e)
        for ema in ['EMA20','EMA50','EMA200']:
            status[ema] = "错误"

    # MACD
    try:
        df = compute_macd(df)
        for col in ['MACD','MACDs','MACDh']:
            if df is not None and col in df.columns:
                status[col] = "OK"
                print(f"\n{col} 前5行:\n", df[col].head())
            else:
                status[col] = "错误"
    except Exception as e:
        print("MACD处理失败:", e)
        for col in ['MACD','MACDs','MACDh']:
            status[col] = "错误"

    # KDJ
    try:
        df = compute_kdj(df)
        for col in ['K','D']:
            if df is not None and col in df.columns:
                status[col] = "OK"
                print(f"\n{col} 前5行:\n", df[col].head())
            else:
                status[col] = "错误"
    except Exception as e:
        print("KDJ处理失败:", e)
        for col in ['K','D']:
            status[col] = "错误"

    # 最终结果
    print("\n=== 指标健康检查结果 (9:30–11:40) ===")
    for k,v in status.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()

