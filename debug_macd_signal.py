# debug_macd_signal.py
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")

# 简化版 MACD + 信号检测调试脚本
def compute_macd_debug(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    print("[DEBUG] MACD列名:", macd.columns.tolist())
    df['MACD'] = macd.iloc[:, 0].fillna(0)
    df['MACDs'] = macd.iloc[:, 1].fillna(0)
    df['MACDh'] = macd.iloc[:, 2].fillna(0)
    return df

def main():
    print("[INFO] 开始调试 MACD 和信号逻辑...")
    df = yf.download(
        "SPY",
        interval="1d",
        period="7d",
        progress=False,
        auto_adjust=True
    )

    if df.empty:
        print("[ERROR] 下载数据为空")
        return

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df.index = df.index.tz_localize("UTC").tz_convert(EST)
    df = compute_macd_debug(df)

    print("\n[DEBUG] 最近几行数据:")
    print(df.tail())

if __name__ == "__main__":
    main()
