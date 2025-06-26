# strategy_refinement_analyzer_backtest.py

import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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

def download_market_data(start, end):
    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, prepost=True, auto_adjust=True)
    if df.empty: raise ValueError("下载失败或数据为空")
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    return df

def analyze_signals(signal_df, market_df):
    if signal_df.empty:
        print("[无信号记录]")
        return
    issues = []

    for _, row in signal_df.iterrows():
        ts = row['timestamp']
        label = row['signal']
        if ts not in market_df.index:
            nearest = market_df.index.get_indexer([ts], method="nearest")[0]
            ts = market_df.index[nearest]
        price = market_df.loc[ts]["Close"]
        after = market_df.loc[ts:ts + timedelta(minutes=30)]
        if after.empty: continue

        high = after["High"].max()
        low = after["Low"].min()

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
    print(f"[🔍 开始分析] {get_est_now().strftime('%Y-%m-%d %H:%M:%S')}")
    df_signals = load_signal_log()
    if df_signals.empty:
        return
    start = df_signals["timestamp"].min() - timedelta(minutes=10)
    end = df_signals["timestamp"].max() + timedelta(minutes=30)
    df_market = download_market_data(start, end)
    analyze_signals(df_signals, df_market)

if __name__ == "__main__":
    main()

