# strategy_refinement_analyzer_backtest.py

import pandas as pd
import yfinance as yf
from datetime import timedelta
from zoneinfo import ZoneInfo

CSV_FILE = "signal_log_backtest.csv"
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

def load_signals():
    df = pd.read_csv(CSV_FILE, parse_dates=["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_localize("America/New_York")
    return df

def download_market_data(start, end):
    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, auto_adjust=True)
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)
    return df

def analyze_signals(signals, market_df):
    issues = []

    for i, row in signals.iterrows():
        ts = row["timestamp"]
        label = row["signal"]
        if ts not in market_df.index:
            nearest_idx = market_df.index.get_indexer([ts], method="nearest")[0]
            ts = market_df.index[nearest_idx]

        price_at_signal = market_df.loc[ts]["Close"]
        future = market_df.loc[ts:ts + timedelta(minutes=30)]
        if future.empty: continue

        high = future["High"].max()
        low = future["Low"].min()

        if "Call" in label:
            if high < price_at_signal * 1.005:
                issues.append((ts, label, "❌ Call 后未涨超 0.5%"))
        elif "Put" in label:
            if low > price_at_signal * 0.995:
                issues.append((ts, label, "❌ Put 后未跌超 0.5%"))

    if issues:
        print("⚠️ 策略潜在问题：")
        for ts, label, reason in issues:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | {label} | {reason}")
    else:
        print("✅ 所有信号延续性良好")

def main():
    signals = load_signals()
    if signals.empty:
        print("❎ 没有找到回测信号")
        return

    start = signals["timestamp"].min() - timedelta(minutes=5)
    end = signals["timestamp"].max() + timedelta(minutes=35)
    market = download_market_data(start, end)
    analyze_signals(signals, market)

if __name__ == "__main__":
    main()
