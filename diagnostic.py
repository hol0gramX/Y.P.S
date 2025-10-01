import yaml
import pandas as pd
import yfinance as yf
import pandas_ta_remake as ta
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ========== 加载配置 ==========
with open("diagnostic_config.yml", "r") as f:
    config = yaml.safe_load(f)

SYMBOL = config['symbol']
EST = ZoneInfo(config['timezone'])
data_start_hour = config['data_start_hour']
lookback_days = config['lookback_days']

rsi_length = config['rsi_length']
rsi_slope_period = config['rsi_slope_period']
ema_lengths = config['ema_lengths']
macd_fast = config['macd_fast']
macd_slow = config['macd_slow']
macd_signal = config['macd_signal']
kdj_length = config['kdj_length']
kdj_signal = config['kdj_signal']
verbose = config.get('verbose', True)

# ========== 时间工具 ==========
def get_est_now():
    return datetime.now(tz=EST)

# ========== 数据拉取 ==========
def get_data():
    now = get_est_now()
    start_time = (now - timedelta(days=lookback_days)).replace(hour=data_start_hour, minute=0, second=0, microsecond=0)
    start_utc = start_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    if df.empty:
        raise ValueError("数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    return df

# ========== 技术指标计算 ==========
def compute_rsi(df):
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(rsi_length).mean() / down.rolling(rsi_length).mean()
    df['RSI'] = (100 - 100 / (1 + rs)).fillna(50)
    df['RSI_SLOPE'] = df['RSI'].diff(rsi_slope_period).fillna(0)
    return df

def compute_ema(df):
    for length in ema_lengths:
        df[f'EMA{length}'] = ta.ema(df['Close'], length=length).fillna(method='bfill')
    return df

def compute_macd(df):
    macd = ta.macd(df['Close'], fast=macd_fast, slow=macd_slow, signal=macd_signal)
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def compute_kdj(df):
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=kdj_length, d=kdj_signal, smooth_k=kdj_signal)
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    return df

# ========== 主诊断 ==========
df = get_data()
df = compute_rsi(df)
df = compute_ema(df)
df = compute_macd(df)
df = compute_kdj(df)

if verbose:
    print("======= 前20行数据 =======")
    print(df.head(20))
    print("======= 后20行数据 =======")
    print(df.tail(20))

# 检查 NaN
nan_counts = df.isna().sum()
print("======= NaN 检查 =======")
print(nan_counts)

# 检查每个指标开盘时是否有效
first_10 = df.head(10)
for col in ['RSI', 'RSI_SLOPE', 'EMA20', 'MACD', 'MACDh', 'K', 'D']:
    print(f"{col} 前10分钟值: {first_10[col].tolist()}")
