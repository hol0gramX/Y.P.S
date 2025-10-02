import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========== 配置 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========== 技术指标计算 ==========
def compute_rsi(series, length=14):
    delta = series.diff()
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

# ========== 数据拉取与诊断 ==========
def diagnose_data_pull_and_indicator():
    try:
        now = datetime.now(tz=EST)
        start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)  # 4点开始
        end_time = now.replace(hour=11, minute=35, second=0, microsecond=0)  # 11:35结束

        print(f"尝试拉取数据时间区间: {start_time} 到 {end_time}")

        start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        # 拉取数据
        df = yf.download(
            SYMBOL, interval="1m", start=start_utc, end=end_utc,
            progress=False, prepost=True, auto_adjust=True
        )

        # 检查数据是否为空
        if df.empty:
            print(f"[错误] 拉取的数据为空: {start_utc} 到 {end_utc}")
            return
        print(f"成功获取数据：{df.head()}")  # 打印前几行数据查看

        # 计算技术指标
        df['RSI'] = compute_rsi(df['Close'])
        df = compute_macd(df)
        df = compute_kdj(df)

        # 打印技术指标
        print("\n计算技术指标（前5行数据）：")
        print(df[['RSI', 'MACD', 'MACDs', 'MACDh', 'K', 'D']].head())

    except Exception as e:
        print(f"[错误] 拉取数据或计算指标时发生错误：{e}")

if __name__ == "__main__":
    diagnose_data_pull_and_indicator()


