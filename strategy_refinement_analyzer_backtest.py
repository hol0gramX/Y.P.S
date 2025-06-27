# strategy_refinement_analyzer_backtest.py (Ready to Commit)

import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas_ta as ta

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
BACKTEST_CSV = "signal_log_backtest.csv"


def get_est_now():
    return datetime.now(tz=EST)


def load_signal_log():
    if not os.path.exists(BACKTEST_CSV):
        print(f"[未找到] 回测文件 {BACKTEST_CSV}")
        return pd.DataFrame()
    df = pd.read_csv(BACKTEST_CSV, parse_dates=['timestamp'])
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize("UTC").dt.tz_convert(EST)
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert(EST)
    return df


def compute_macd(df):
    try:
        macd = ta.macd(df['Close'])
        if macd is None or macd.isna().all().all():
            print("[⚠️] MACD计算失败")
            df['MACD'] = df['MACDs'] = df['MACDh'] = 0
        else:
            df['MACD'] = macd['MACD_12_26_9'].fillna(0)
            df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
            df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    except Exception:
        print("[⚠️] MACD计算异常")
        df['MACD'] = df['MACDs'] = df['MACDh'] = 0
    return df


def compute_rsi(df):
    try:
        rsi = ta.rsi(df['Close'], length=14)
        if rsi is None or rsi.isna().all():
            print("[⚠️] RSI计算失败，使用默认值")
            df['RSI'] = 50
        else:
            df['RSI'] = rsi.fillna(50)
    except Exception:
        print("[⚠️] RSI计算异常，使用默认值")
        df['RSI'] = 50
    return df


def download_market_data(start, end):
    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, prepost=True, auto_adjust=True)
    if df.empty:
        raise ValueError("下载失败或数据为空")
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    df = compute_rsi(df)
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df


def analyze_signals(signal_df, market_df):
    if signal_df.empty:
        print("[信息] 无信号记录")
        return

    print("\n[📊 分析回测信号]")
    issues = []

    for _, row in signal_df.iterrows():
        ts = row['timestamp']
        label = row['signal']

        # 获取最接近的实际行情时间戳
        if ts not in market_df.index:
            nearest = market_df.index.get_indexer([ts], method="nearest")[0]
            ts = market_df.index[nearest]

        try:
            price = market_df.loc[ts]["Close"]
            if isinstance(price, pd.Series):
                price = price.iloc[0]
        except Exception:
            print(f"[⚠️] 无法获取 {ts} 的价格")
            continue

        after = market_df.loc[ts:ts + timedelta(minutes=30)]
        if after.empty:
            continue

        high = after["High"].max()
        low = after["Low"].min()

        if isinstance(high, pd.Series): high = high.iloc[0]
        if isinstance(low, pd.Series): low = low.iloc[0]

        if "Call" in label:
            if high < price * 1.005:
                issues.append((ts, label, "Call信号后无上涨延续"))
        elif "Put" in label:
            if low > price * 0.995:
                issues.append((ts, label, "Put信号后无下跌延续"))

    if issues:
        print("[⚠️ 回测分析结果] 存在可能问题信号：")
        for ts, label, reason in issues:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | {label} | ⚠️ {reason}")
    else:
        print("[✅ 回测分析] 所有信号行为合理，无明显缺陷")


def main():
    print(f"[🔍 分析启动] {get_est_now().strftime('%Y-%m-%d %H:%M:%S')}")
    df_signals = load_signal_log()
    if df_signals.empty:
        return
    start = df_signals["timestamp"].min() - timedelta(minutes=10)
    end = df_signals["timestamp"].max() + timedelta(minutes=30)
    df_market = download_market_data(start, end)
    analyze_signals(df_signals, df_market)


if __name__ == "__main__":
    main()
