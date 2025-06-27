# strategy_refinement_analyzer_backtest.py (with suggestion engine)

import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas_ta as ta

SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
BACKTEST_CSV = "signal_log_backtest.csv"
REPORT_FILE = "signal_analysis_report.txt"
MISSED_TRENDS_FILE = "missed_trends_report.txt"
SUGGESTIONS_FILE = "strategy_improvement_suggestions.txt"


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
    if df.empty:
        raise ValueError("下载失败或数据为空")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()


def compute_rsi(s, length=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.rolling(length).mean() / down.rolling(length).mean()
    return (100 - 100 / (1 + rs)).fillna(50)


def compute_macd(df):
    macd = ta.macd(df['Close'])
    df['MACD'] = macd['MACD_12_26_9'].fillna(0)
    df['MACDs'] = macd['MACDs_12_26_9'].fillna(0)
    df['MACDh'] = macd['MACDh_12_26_9'].fillna(0)
    return df


def analyze_signals(signal_df, market_df):
    if signal_df.empty:
        print("[无信号记录]")
        return []

    issues = []
    results = []

    for _, row in signal_df.iterrows():
        ts = row['timestamp']
        label = row['signal']

        if ts not in market_df.index:
            nearest = market_df.index.get_indexer([ts], method="nearest")[0]
            ts = market_df.index[nearest]

        price = market_df.loc[ts]["Close"]
        after = market_df.loc[ts:ts + timedelta(minutes=30)]
        if after.empty:
            continue

        high = after["High"].max()
        low = after["Low"].min()
        rsi = market_df.loc[ts]["RSI"]
        macdh = market_df.loc[ts]["MACDh"]

        call_strength = (high - price) / price
        put_strength = (price - low) / price

        if "Call" in label:
            if call_strength < 0.005:
                issues.append((ts, label, f"Call信号无延续 | RSI:{rsi:.1f}, MACDh:{macdh:.2f}"))
            strength_tag = "强" if call_strength >= 0.015 else ("中" if call_strength >= 0.008 else "弱")
            results.append(f"{ts.strftime('%Y-%m-%d %H:%M')} | {label} | 强度：{strength_tag} | ↗ 涨幅:{call_strength*100:.2f}% | RSI:{rsi:.1f} MACDh:{macdh:.2f}")
        elif "Put" in label:
            if put_strength < 0.005:
                issues.append((ts, label, f"Put信号无延续 | RSI:{rsi:.1f}, MACDh:{macdh:.2f}"))
            strength_tag = "强" if put_strength >= 0.015 else ("中" if put_strength >= 0.008 else "弱")
            results.append(f"{ts.strftime('%Y-%m-%d %H:%M')} | {label} | 强度：{strength_tag} | ↘ 跌幅:{put_strength*100:.2f}% | RSI:{rsi:.1f} MACDh:{macdh:.2f}")

    if issues:
        print("[⚠️ 回测分析] 存在问题信号：")
        for ts, label, reason in issues:
            print(f"- {ts.strftime('%Y-%m-%d %H:%M')} | {label} | ⚠️ {reason}")
    else:
        print("[✅ 回测分析] 所有信号合理")

    return results


def find_missed_trends(market_df, signal_df):
    missed = []
    detail_rows = []
    signal_times = set(signal_df['timestamp'])
    market_df['return'] = market_df['Close'].pct_change().fillna(0)

    window = 30
    threshold = 0.008

    for i in range(len(market_df) - window):
        start = market_df.index[i]
        end = market_df.index[i + window]
        segment = market_df.loc[start:end]
        pct_change = (segment['Close'][-1] - segment['Close'][0]) / segment['Close'][0]

        if abs(pct_change) >= threshold:
            has_signal = any((start <= ts <= end) for ts in signal_times)
            if not has_signal:
                direction = "上涨" if pct_change > 0 else "下跌"
                rsi_avg = segment['RSI'].mean()
                macdh_avg = segment['MACDh'].mean()
                missed.append(f"{start.strftime('%H:%M')} ~ {end.strftime('%H:%M')} | {direction}段 | 幅度：{pct_change*100:.2f}% | ⚠️ 无信号捕捉")
                detail_rows.append((start, end, pct_change, rsi_avg, macdh_avg, direction))

    return missed, detail_rows


def generate_suggestions(detail_rows):
    suggestions = []
    for start, end, pct, rsi_avg, macdh_avg, direction in detail_rows:
        if direction == "上涨" and rsi_avg > 50 and macdh_avg > 0:
            suggestions.append(f"🔧 建议：上涨段 {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')} 平均RSI={rsi_avg:.1f}, MACDh={macdh_avg:.2f}，可考虑放宽 Call 入场 RSI 至 {int(rsi_avg) - 2} 附近。")
        elif direction == "下跌" and rsi_avg < 50 and macdh_avg < 0:
            suggestions.append(f"🔧 建议：下跌段 {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')} 平均RSI={rsi_avg:.1f}, MACDh={macdh_avg:.2f}，可考虑放宽 Put 入场 RSI 至 {int(rsi_avg) + 2} 附近。")
    return suggestions


def write_report(lines, filename):
    with open(filename, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    print(f"[✅ 报告保存] {filename}")


def main():
    print(f"[🔍 分析启动] {get_est_now().strftime('%Y-%m-%d %H:%M:%S')}")
    df_signals = load_signal_log()
    if df_signals.empty:
        return
    start = df_signals["timestamp"].min() - timedelta(minutes=10)
    end = df_signals["timestamp"].max() + timedelta(minutes=30)
    df_market = download_market_data(start, end)

    result_lines = analyze_signals(df_signals, df_market)
    missed_lines, missed_rows = find_missed_trends(df_market, df_signals)
    suggestions = generate_suggestions(missed_rows)

    if result_lines:
        write_report(result_lines, REPORT_FILE)
    if missed_lines:
        write_report(missed_lines, MISSED_TRENDS_FILE)
    if suggestions:
        write_report(suggestions, SUGGESTIONS_FILE)


if __name__ == "__main__":
    main()
