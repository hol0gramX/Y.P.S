import yfinance as yf
import pandas as pd
from datetime import datetime
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
    if macd is None or macd.empty:
        print("⚠️ 传入空数据，MACD计算跳过")
        return df
    df['MACD'] = macd['MACD_5_10_20'].fillna(0)
    df['MACDs'] = macd['MACDs_5_10_20'].fillna(0)
    df['MACDh'] = macd['MACDh_5_10_20'].fillna(0)
    return df

def fetch_data_dynamic_window(test_datetime=None):
    if test_datetime:
        now = test_datetime.astimezone(EST)
    else:
        now = datetime.now(tz=EST)

    start_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    end_time = now

    print(f"⌛ 拉取数据时间段（EST）：{start_time} 到 {end_time}")

    # 转成UTC给yf用
    start_utc = start_time.astimezone(ZoneInfo("UTC"))
    end_utc = end_time.astimezone(ZoneInfo("UTC"))

    print(f"⌛ 转换为UTC给yfinance拉数据：{start_utc} 到 {end_utc}")

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
        print("⚠️ yf拉取数据为空")
        return None

    print(f"✅ 拉取数据成功，条数: {len(df)}")
    print("数据索引样例（前5条）：")
    print(df.index[:5])

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["High", "Low", "Close", "Volume"])
    df = df[df["Volume"] > 0]

    # 确保索引是带时区的UTC时间，转换到EST时区
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    print(f"df.index tzinfo (转换后): {df.index.tz}")

    # 下面这部分修改，转成无时区datetime进行过滤，避免时区不匹配导致过滤空数据
    start_time_naive = start_time.replace(tzinfo=None)
    end_time_naive = end_time.replace(tzinfo=None)

    df.index = df.index.tz_convert(None)  # 转成naive datetime索引

    print(f"过滤前数据条数: {len(df)}")
    df = df[(df.index >= start_time_naive) & (df.index < end_time_naive)]
    print(f"过滤后有效数据条数: {len(df)}")

    if df.empty:
        print("⚠️ 过滤后无有效数据")
        return None

    # 计算指标
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['RSI_SLOPE'] = df['RSI'].diff(3)
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)

    # 可能计算指标时仍会有NaN，使用ffill填充
    df.ffill(inplace=True)
    df.dropna(subset=["High", "Low", "Close", "Volume", "VWAP", "RSI", "MACD", "MACDh"], inplace=True)

    if df.empty:
        print("⚠️ 指标计算后无有效数据")
        return None

    return df

def main():
    # 模拟 2025年6月27日 9:30:00 EST
    test_time_est = datetime(2025, 6, 27, 9, 30, 0, tzinfo=EST)
    print(f"🕒 模拟时间点: {test_time_est}")

    df = fetch_data_dynamic_window(test_time_est)

    if df is None or df.empty:
        print("❌ 未获取到有效数据，退出")
        return

    print(f"✅ 模拟时间点：{test_time_est.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"数据总条数: {len(df)}")
    print(f"起始时间: {df.index[0].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"结束时间: {df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}")

    last_row = df.iloc[-1]
    print("\n📊 9:30 时刻最新一条数据：")
    print(f"时间: {df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Close: {last_row['Close']:.2f} | Volume: {last_row['Volume']}")
    print(f"Vol_MA5: {last_row['Vol_MA5']:.2f} | RSI: {last_row['RSI']:.2f} | RSI_SLOPE: {last_row['RSI_SLOPE']:.3f}")
    print(f"VWAP: {last_row['VWAP']:.2f} | MACD: {last_row['MACD']:.3f} | MACDh: {last_row['MACDh']:.3f}")

if __name__ == "__main__":
    main()
