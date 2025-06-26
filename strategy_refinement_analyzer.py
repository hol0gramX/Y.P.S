import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ----------- 配置 -----------
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")

# ----------- 工具函数 -----------
def get_est_now():
    return datetime.now(tz=EST)

def load_signal_log(file_path):
    if not os.path.exists(file_path):
        print(f"[信息] 未找到信号文件：{file_path}")
        return pd.DataFrame()
    df = pd.read_csv(file_path, parse_dates=['timestamp'])
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize("UTC").dt.tz_convert(EST)
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert(EST)
    return df

def download_market_data():
    end = get_est_now()
    start = end - timedelta(days=3)
    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, prepost=True, auto_adjust=True)
    if df.empty:
        raise ValueError("下载的数据为空")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)
    return df

def analyze_signals(signal_df, market_df):
    if signal_df.empty:
        print("[信息] 无信号记录可分析")
        return

    issues = []

    for i, row in signal_df.iterrows():
        ts = row['timestamp']
        label = row['signal']

        if ts not in market_df.index:
            nearest_idx = market_df.index.get_indexer([ts], method='nearest')[0]
            ts = market_df.index[nearest_idx]

        price_at_signal = market_df.loc[ts]['Close']
        after_slice = market_df.loc[ts:ts + timedelta(minutes=30)]
        if after_slice.empty:
            continue

        high_after = after_slice['High'].max()
        low_after = after_slice['Low'].min()

        if "Call" in label:
            if high_after < price_at_signal * 1.005:
                issues.append((ts, label, "Call信号后无上涨延续"))
        elif "Put" in label:
            if low_after > price_at_signal * 0.995:
                issues.append((ts, label, "Put信号后无下跌延续"))

    if issues:
        print("[分析结果] ⚠️ 策略潜在问题：")
        for ts, label, reason in issues:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | {label} | ⚠️ {reason}")
    else:
        print("[分析结果] ✅ 所有信号行为合理，无明显缺陷")

# ----------- 主流程 -----------
def main():
    try:
        now = get_est_now()
        print(f"[DEBUG] 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # 自动定位今天的 signal log 文件
        today_str = now.strftime("%Y-%m-%d")
        file_path = f"signal_log_{today_str}.csv"

        signals = load_signal_log(file_path)
        market = download_market_data()
        analyze_signals(signals, market)

    except Exception as e:
        print("[错误] 分析失败：", e)

if __name__ == "__main__":
    main()

