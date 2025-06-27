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
    df['timestamp'] = df['timestamp'].dt.tz_localize("UTC").dt.tz_convert(EST) if df['timestamp'].dt.tz is None else df['timestamp'].dt.tz_convert(EST)
    return df

def compute_macd(df):
    if len(df) < 30:
        print("[⚠️] 行数不足，跳过MACD计算")
        df['MACD'] = df['MACDs'] = df['MACDh'] = 0
        return df
    macd = ta.macd(df['Close'])
    if macd is None or not isinstance(macd, pd.DataFrame):
        print("[⚠️] MACD计算失败")
        df['MACD'] = df['MACDs'] = df['MACDh'] = 0
        return df
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df

def download_market_data(start, end):
    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, prepost=True, auto_adjust=True)
    if df.empty:
        raise ValueError("下载数据为空")
    df.index = df.index.tz_localize("UTC").tz_convert(EST) if df.index.tz is None else df.index.tz_convert(EST)

    # 计算 MACD
    df = compute_macd(df)

    # 计算 RSI（防止 None 报错）
    rsi = ta.rsi(df['Close'], length=14)
    if rsi is None or not isinstance(rsi, pd.Series):
        print("[⚠️] RSI计算失败，使用默认值")
        df['RSI'] = 50
    else:
        df['RSI'] = rsi.fillna(50)

    # VWAP
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    return df


def analyze_signals(signal_df, market_df):
    print("\n[📊 分析回测信号]")
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
        print("[⚠️ 检出问题信号]")
        for ts, label, reason in issues:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | {label} | ⚠️ {reason}")
    else:
        print("[✅ 所有信号表现良好]")

def detect_missed_opportunities(signal_df, market_df):
    print("\n[📈 检测漏掉的主升/主跌段]")
    signal_times = set(signal_df['timestamp'])
    missed = []
    for i in range(30, len(market_df) - 30):
        win = market_df.iloc[i:i+30]
        change = (win['Close'].iloc[-1] - win['Close'].iloc[0]) / win['Close'].iloc[0]
        ts = win.index[0]
        if any(abs((ts - t).total_seconds()) < 1800 for t in signal_times): continue
        if change > 0.007:
            missed.append((ts, f"上涨 {change:.2%}"))
        elif change < -0.007:
            missed.append((ts, f"下跌 {change:.2%}"))
    if missed:
        for ts, info in missed:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | ❌ 未捕捉 {info}")
    else:
        print("[✅ 所有大波段都已被信号覆盖]")

def suggest_improvements(signal_df, market_df):
    print("\n[🛠️ 策略指标建议]")
    recent = market_df.loc[signal_df['timestamp'].min():]
    avg_rsi = recent['RSI'].mean()
    avg_macdh = recent['MACDh'].mean()

    if avg_rsi > 60:
        print("- 🎯 RSI门槛略高，可能放宽入场条件")
    elif avg_rsi < 45:
        print("- 🎯 RSI门槛偏低，建议加强过滤防止误入")
    if avg_macdh < 0.05:
        print("- 🎯 MACD动能偏弱，可考虑动态调整入场阈值")
    else:
        print("- ✅ RSI与MACD平均表现正常")

def main():
    print(f"[🔍 分析启动] {get_est_now().strftime('%Y-%m-%d %H:%M:%S')}")
    df_signals = load_signal_log()
    if df_signals.empty:
        return
    start = df_signals["timestamp"].min() - timedelta(minutes=10)
    end = df_signals["timestamp"].max() + timedelta(minutes=45)
    df_market = download_market_data(start, end)

    analyze_signals(df_signals, df_market)
    detect_missed_opportunities(df_signals, df_market)
    suggest_improvements(df_signals, df_market)

if __name__ == "__main__":
    main()
