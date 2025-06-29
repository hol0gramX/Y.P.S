import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, time
from zoneinfo import ZoneInfo

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

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

def fetch_data_around_open(date_str):
    # 拉取当日4:00 - 10:00数据（包含盘前与开盘）
    from datetime import timedelta
    start_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=EST).replace(hour=4, minute=0, second=0, microsecond=0)
    end_dt = start_dt.replace(hour=10, minute=0)

    start_utc = start_dt.astimezone(ZoneInfo("UTC"))
    end_utc = end_dt.astimezone(ZoneInfo("UTC"))

    df = yf.download(
        SYMBOL,
        interval="1m",
        start=start_utc,
        end=end_utc,
        progress=False,
        prepost=True,
        auto_adjust=True,
    )

    if df.empty:
        raise ValueError("无数据")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.index = df.index.tz_localize("UTC").tz_convert(EST)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]

    # 计算指标
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)

    df.ffill(inplace=True)
    df.dropna(subset=["VWAP", "RSI", "MACD", "MACDh"], inplace=True)

    # 找9:30这一分钟的索引位置
    open_time = time(9, 30)
    idx_930 = df.index.get_loc(df[df.index.time == open_time].index[0])

    # 向上取20分钟（或者如果不足则取全部）
    start_idx = max(0, idx_930 - 20)
    df_slice = df.iloc[start_idx:idx_930 + 1]

    return df_slice

if __name__ == "__main__":
    import sys
    date_str = datetime.now(EST).strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        date_str = sys.argv[1]

    print(f"调试 {SYMBOL} {date_str} 9:30分钟及前20分钟指标")
    df_slice = fetch_data_around_open(date_str)

    for ts, row in df_slice.iterrows():
        print(
            f"{ts.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
            f"Close={row['Close']:.2f} Vol={int(row['Volume'])} Vol_MA5={row['Vol_MA5']:.1f} "
            f"VWAP={row['VWAP']:.2f} RSI={row['RSI']:.1f} RSI_Slope={row['RSI_SLOPE']:.3f} "
            f"MACD={row['MACD']:.3f} MACDh={row['MACDh']:.3f}"
        )
