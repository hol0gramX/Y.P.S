import yfinance as yf
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas_ta as ta

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

def fetch_data_fixed_date():
    start_time = datetime(2025, 6, 20, 4, 0, 0, tzinfo=EST)
    end_time = datetime(2025, 6, 20, 10, 0, 0, tzinfo=EST)

    # 转成UTC给yf用
    start_utc = start_time.astimezone(ZoneInfo("UTC"))
    end_utc = end_time.astimezone(ZoneInfo("UTC"))

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
        print("无数据")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # 只保留当天数据，且限制时间段（4:00-10:00 EST）
    df = df[(df.index >= start_time) & (df.index < end_time)]

    # 计算指标
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)

    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "Volume", "VWAP", "RSI", "MACD", "MACDh"], inplace=True)

    return df

def main():
    df = fetch_data_fixed_date()
    if df is None:
        return

    print(f"数据总条数: {len(df)}")
    # 打印开盘后30分钟数据（9:30 - 10:00）
    start_print = datetime(2025, 6, 20, 9, 30, 0, tzinfo=EST)
    end_print = datetime(2025, 6, 20, 10, 0, 0, tzinfo=EST)

    df_print = df[(df.index >= start_print) & (df.index < end_print)]

    print("开盘后前30分钟指标：")
    for ts, row in df_print.iterrows():
        print(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} | Close: {row['Close']:.2f} | Volume: {row['Volume']} | Vol_MA5: {row['Vol_MA5']:.2f} | RSI: {row['RSI']:.2f} | RSI_SLOPE: {row['RSI_SLOPE']:.3f} | VWAP: {row['VWAP']:.2f} | MACD: {row['MACD']:.3f} | MACDh: {row['MACDh']:.3f}")

if __name__ == "__main__":
    main()

