import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo

# ========== 全局配置 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ========== 时间工具 ==========
def get_est_now():
    return datetime.now(tz=EST)

# ========== 技术指标计算 ==========
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

# ========== 数据拉取与指标计算 ==========
def get_data_accumulated():
    now = get_est_now()
    today = now.date()

    # 从当天 4:00 到当前时间
    start_dt = datetime.combine(today, time(4,0), tzinfo=EST)
    start_utc = start_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL, interval="1m", start=start_utc, end=end_utc,
        progress=False, prepost=True, auto_adjust=True
    )
    if df.empty:
        print("❌ 没有拉到数据")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High","Low","Close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)

    df.ffill(inplace=True)
    df.dropna(subset=["RSI","MACD","MACDh","EMA20","K","D"], inplace=True)

    # 截取 9:30–11:30
    df = df.between_time("09:30","11:30")
    return df

# ========== 诊断打印 ==========
def diagnose():
    df = get_data_accumulated()
    if df is None:
        return
    print("✅ 诊断输出：今天 9:30–11:30 前 20 行技术指标（累计自 4:00）\n")
    print(df[['Close','RSI','RSI_SLOPE','MACD','MACDs','MACDh','EMA20','K','D']].head(20))

if __name__ == "__main__":
    diagnose()

