import yfinance as yf
import pandas_ta as ta
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

target_date = "2025-07-01"
start_time = "09:55:00"
end_time = "09:56:00"

# 构造时间对象（带时区）
start_dt = datetime.strptime(f"{target_date} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=EST)
end_dt = datetime.strptime(f"{target_date} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=EST)

# 转换为UTC无时区（yfinance要求）
start_utc = start_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
end_utc = end_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

# 下载数据
df = yf.download(
    SYMBOL,
    interval="1m",
    start=start_utc,
    end=end_utc,
    progress=False,
    auto_adjust=True,
    prepost=False
)

# 转换为东部时间
if df.index.tz is None:
    df.index = df.index.tz_localize("UTC").tz_convert(EST)
else:
    df.index = df.index.tz_convert(EST)

# 计算指标函数
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

# 计算指标
df['RSI'] = compute_rsi(df['Close'])
df['RSI_SLOPE'] = df['RSI'].diff(3)
df['EMA20'] = ta.ema(df['Close'], length=20)
df = compute_macd(df)
df.ffill(inplace=True)
df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20"], inplace=True)

print(df)
