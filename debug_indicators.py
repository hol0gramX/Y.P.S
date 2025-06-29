import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========== 参数 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
now = datetime.now(tz=EST)
start_time = now - timedelta(days=1)

# ========== 拉数据 ==========
print("⏳ 正在拉取数据中...")
df = yf.download(
    SYMBOL,
    start=start_time.astimezone(ZoneInfo("UTC")),
    end=now.astimezone(ZoneInfo("UTC")),
    interval="1m",
    prepost=True,
    auto_adjust=True,
    progress=False
)

if df.empty:
    print("❌ 拉取失败，数据为空")
    exit()

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df = df.dropna(subset=["High", "Low", "Close", "Volume"])
df = df[df["Volume"] > 0]

if df.index.tz is None:
    df.index = df.index.tz_localize("UTC").tz_convert(EST)
else:
    df.index = df.index.tz_convert(EST)

# ========== 计算指标 ==========
df['Vol_MA5'] = df['Volume'].rolling(5).mean()
df['RSI'] = ta.rsi(df['Close'], length=14).fillna(50)
df['RSI_SLOPE'] = df['RSI'].diff(3)
df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

macd = ta.macd(df['Close'], fast=5, slow=10, signal=20)
print("🧪 MACD 列名:", macd.columns.tolist())
df['MACD'] = macd['MACD_5_10_20'].fillna(0)
df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)

# ========== 打印调试信息 ==========
print("\n✅ 最后5行完整数据（含主要指标）:")
print(df[["Close", "Volume", "Vol_MA5", "RSI", "RSI_SLOPE", "VWAP", "MACD", "MACDh", "MACDs"]].tail(5))

print("\n📊 检查空值数量:")
print(df[["Vol_MA5", "RSI", "RSI_SLOPE", "VWAP", "MACD", "MACDh"]].isnull().sum())

print("\n📈 数据总行数（未 dropna）:", len(df))
