import yfinance as yf
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

target_date = "2025-07-01"
start_dt = datetime.strptime(f"{target_date} 04:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=EST)
end_dt = datetime.strptime(f"{target_date} 09:56:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=EST)

# 转换为UTC无时区（yfinance要求）
start_utc = start_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
end_utc = end_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

# 拉取数据，包含盘前盘后，auto_adjust调整后价格
df = yf.download(
    SYMBOL,
    interval="1m",
    start=start_utc,
    end=end_utc,
    progress=False,
    auto_adjust=True,
    prepost=True
)

# 处理MultiIndex列（如果有）
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 丢弃重要列缺失行
df = df.dropna(subset=["High", "Low", "Close"])

# 统一转为东部时间
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
    if macd is None:
        print("MACD计算失败，返回None，填充0")
        df['MACD'] = 0
        df['MACDs'] = 0
        df['MACDh'] = 0
        return df
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

# 计算指标
df['RSI'] = compute_rsi(df['Close'])
df['RSI_SLOPE'] = df['RSI'].diff(3)
df['EMA20'] = ta.ema(df['Close'], length=20)
df = compute_macd(df)

# 向前填充缺失指标，丢弃还缺失重要指标的行
df.ffill(inplace=True)
df.dropna(subset=["High", "Low", "Close", "RSI", "MACD", "MACDh", "EMA20"], inplace=True)

# 只打印9:55和9:56这两分钟的所有指标和价格，方便调参
print(df.loc[(df.index.time == time(9,55)) | (df.index.time == time(9,56))])

