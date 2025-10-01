import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

# ====== 技术指标计算函数 ======

def compute_rsi(s, length=14):
    try:
        print("正在计算 RSI...")
        delta = s.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        rs = up.rolling(length).mean() / down.rolling(length).mean()
        rsi = (100 - 100 / (1 + rs)).fillna(50)
        print("RSI 计算成功")
        return rsi
    except Exception as e:
        print(f"计算 RSI 失败: {e}")
        return pd.Series([None] * len(s))

def compute_macd(df):
    try:
        print("正在计算 MACD...")
        macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
        if macd is not None:
            df['MACD'] = macd['MACD_5_10_20'].fillna(0)
            df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
            df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
            print("MACD 计算成功")
        else:
            print("MACD 计算失败，返回 None")
    except Exception as e:
        print(f"计算 MACD 失败: {e}")
    return df

def compute_kdj(df):
    try:
        print("正在计算 KDJ...")
        kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3, smooth_k=3)
        df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
        df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
        print("KDJ 计算成功")
    except Exception as e:
        print(f"计算 KDJ 失败: {e}")
    return df

def compute_ema(df):
    try:
        print("正在计算 EMA...")
        df['EMA20'] = ta.ema(df['Close'], length=20)
        df['EMA50'] = ta.ema(df['Close'], length=50)
        df['EMA200'] = ta.ema(df['Close'], length=200)
        print("EMA 计算成功")
    except Exception as e:
        print(f"计算 EMA 失败: {e}")
    return df

# ====== 主函数 ======
def main():
    print("开始抓取 9:30–11:40 数据并计算指标…")
    
    try:
        df = yf.download(
            "SPY", interval="1m", period="1d", progress=False, prepost=True, auto_adjust=True
        )
        
        if df.empty:
            print("数据为空，无法计算指标")
            return

        # 转时区
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(EST)
        else:
            df.index = df.index.tz_convert(EST)

        # 选取 9:30–11:40
        df = df.between_time("09:30", "11:40")
        print(f"9:30–11:40 数据行数: {len(df)}\n")

        # 检查数据是否完整
        if df.isnull().any().any():
            print("数据存在缺失值，请检查数据完整性")
            print(df.isnull().sum())
            return

        # 计算指标并诊断
        print("计算各项技术指标…")
        df['RSI'] = compute_rsi(df['Close'])
        df = compute_ema(df)
        df = compute_macd(df)
        df = compute_kdj(df)

        # 检查指标计算结果
        print("前20行数据及计算指标：\n")
        print(df[['Open', 'High', 'Low', 'Close', 'RSI', 'EMA20', 'MACD', 'MACDh', 'K', 'D']].head(20))

    except Exception as e:
        print(f"运行过程中发生错误: {e}")

if __name__ == "__main__":
    main()

