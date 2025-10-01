import yaml
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas_ta_remake as ta  # 确保这个包能用

# ========== 读取配置 ==========
with open("diagnostic_config.yml", "r") as f:
    cfg = yaml.safe_load(f)

SYMBOL = cfg["symbol"]
EST = ZoneInfo(cfg["timezone"])
DATA_START_HOUR = cfg["data_start_hour"]
LOOKBACK_DAYS = cfg["lookback_days"]
VERBOSE = cfg.get("verbose", True)

# ========== 工具 ==========
def get_est_now():
    return datetime.now(tz=EST)

def get_data():
    now = get_est_now()
    start = now.replace(hour=DATA_START_HOUR, minute=0, second=0, microsecond=0)
    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start,
        end=now,
        progress=False,
        prepost=True,
        auto_adjust=True
    )
    if df.empty:
        raise ValueError("数据为空")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    return df

# ========== 指标计算 ==========
def compute_indicators(df):
    df['RSI'] = ta.rsi(df['Close'], length=cfg["rsi_length"])
    df['RSI_SLOPE'] = df['RSI'].diff(cfg["rsi_slope_period"])
    for ema_len in cfg["ema_lengths"]:
        df[f'EMA{ema_len}'] = ta.ema(df['Close'], length=ema_len)
    macd = ta.macd(df['Close'], fast=cfg["macd_fast"], slow=cfg["macd_slow"], signal=cfg["macd_signal"])
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    kdj = ta.stoch(df['High'], df['Low'], df['Close'], k=cfg["kdj_length"], d=cfg["kdj_signal"], smooth_k=cfg["kdj_signal"])
    df['K'] = kdj['STOCHk_9_3_3'].fillna(50)
    df['D'] = kdj['STOCHd_9_3_3'].fillna(50)
    df.ffill(inplace=True)
    return df

# ========== 诊断函数 ==========
def diagnose(df):
    for i, row in df.iterrows():
        reasons = []
        if row['Close'] > row['EMA20']:
            reasons.append("Close>EMA20")
        if row['RSI'] > 53:
            reasons.append("RSI>53")
        if row['MACD'] > 0:
            reasons.append("MACD>0")
        if row['MACDh'] > 0:
            reasons.append("MACDh>0")
        if row['RSI_SLOPE'] > 0.15:
            reasons.append("RSI_SLOPE>0.15")

        if len(reasons) < 5:
            print(f"[{i.strftime('%H:%M')}] ❌ 没信号，原因缺失：{set(['Close>EMA20','RSI>53','MACD>0','MACDh>0','RSI_SLOPE>0.15']) - set(reasons)}")
        else:
            print(f"[{i.strftime('%H:%M')}] ✅ 可以触发信号，全部条件满足")

# ========== 主程序 ==========
if __name__ == "__main__":
    df = get_data()
    df = compute_indicators(df)
    diagnose(df)

