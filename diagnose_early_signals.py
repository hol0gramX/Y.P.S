import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# ==== 设置打印选项（避免省略号，显示所有行列完整数值）====
pd.set_option('display.max_columns', None)   # 显示所有列
pd.set_option('display.max_rows', None)      # 显示所有行（注意：数据多时很长）
pd.set_option('display.max_colwidth', None)  # 列宽不截断
pd.set_option('display.float_format', lambda x: '%.6f' % x)  # 小数完整显示

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ==== 技术指标 ====
def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
    df['MACD'] = macd['MACD_5_10_20']
    df['MACDs'] = macd['MACDs_5_10_20']
    df['MACDh'] = macd['MACDh_5_10_20']
    return df

def compute_kdj(df, length=9, signal=3):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=length, d=signal, smooth_k=signal)
    df['K'] = kdj['STOCHk_9_3_3']
    df['D'] = kdj['STOCHd_9_3_3']
    return df

# ==== 拉取数据 ====
def fetch_data():
    now = datetime.now(tz=EST)
    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL, interval="1m", start=start_utc, end=end_utc,
        prepost=True, auto_adjust=True, progress=False
    )

    if df.empty:
        print("❌ 无数据，检查 yfinance 是否拉取成功")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df = compute_macd(df)
    df = compute_kdj(df)

    return df

# ==== 排查逻辑 ====
def troubleshoot():
    df = fetch_data()
    if df is None:
        return

    print(f"✅ 共拉取 {len(df)} 条数据，时间范围：{df.index[0]} ~ {df.index[-1]}")

    # 检查前 50 条指标情况（完整显示）
    print("\n=== 前 50 根K线指标检查 ===")
    cols = ["Close", "RSI", "MACD", "MACDh", "K", "D"]
    print(df[cols].head(50))   # 不会再出现省略号

    # 检查每个指标首次有效时间
    print("\n=== 每个指标首次非空时间 ===")
    for col in ["RSI", "RSI_SLOPE", "EMA20", "MACD", "MACDh", "K", "D"]:
        valid = df[col].first_valid_index()
        print(f"{col:<8} → {valid}")

    # 检查所有指标齐全的最早时间
    complete_idx = df.dropna(subset=["RSI","RSI_SLOPE","EMA20","MACD","MACDh","K","D"]).index
    if not complete_idx.empty:
        print(f"\n📌 所有指标首次齐全的时间：{complete_idx[0]}")
    else:
        print("\n⚠️ 整个区间没有找到所有指标齐全的时间")

if __name__ == "__main__":
    troubleshoot()


