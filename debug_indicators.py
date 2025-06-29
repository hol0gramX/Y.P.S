import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

# ========== 参数 ==========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========== 获取最近交易日 ==========
def get_last_trading_day(date):
    sched = nasdaq.schedule(start_date=date - timedelta(days=7), end_date=date)
    if sched.empty:
        return None
    return sched.index[-1].date()

now = datetime.now(tz=EST)
last_trading_day = get_last_trading_day(now.date())

if not last_trading_day:
    print("过去7天无交易日，无法获取数据")
    exit()

# ========== 设置当天盘前4点到16点区间 ==========
start_dt = datetime.combine(last_trading_day, time(4, 0), tzinfo=EST)
end_dt = datetime.combine(last_trading_day, time(16, 0), tzinfo=EST)

# ========== 拉数据 ==========
print(f"⏳ 正在拉取 {last_trading_day} 的1分钟数据...")
df = yf.download(
    SYMBOL,
    start=start_dt.astimezone(ZoneInfo("UTC")),
    end=end_dt.astimezone(ZoneInfo("UTC")),
    interval="1m",
    prepost=True,
    auto_adjust=True,
    progress=False,
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
