# strategy_refinement_analyzer.py

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import json

# -------- CONFIG --------
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
REPORT_FILE = "refinement_report.txt"

# -------- Load Today Data --------
def get_today_data():
    today = datetime.now(tz=EST).date()
    start = datetime.combine(today, datetime.min.time()).astimezone(EST)
    end = start + timedelta(days=1)

    df = yf.download(SYMBOL, interval="1m", start=start, end=end, progress=False, prepost=True)
    df.index = df.index.tz_localize("UTC").tz_convert(EST)
    df = df.dropna(subset=["Close", "Volume"])
    return df

# -------- Compute Indicators --------
def compute_indicators(df):
    df['RSI'] = df['Close'].diff().apply(lambda x: x if x > 0 else 0).rolling(14).mean() / \
                df['Close'].diff().apply(lambda x: -x if x < 0 else 0).rolling(14).mean()
    df['RSI'] = 100 - 100 / (1 + df['RSI'])
    macd_line = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    df['MACD'] = macd_line
    df['MACDs'] = signal_line
    df['MACDh'] = df['MACD'] - df['MACDs']
    return df

# -------- Analyze Missed Opportunities --------
def analyze_missed_signals(df):
    report = []
    window = 30  # lookback for swing detection

    max_up = df['Close'].rolling(window).max()
    min_down = df['Close'].rolling(window).min()

    large_up = ((max_up - df['Close']) / df['Close'] < -0.015)
    large_down = ((df['Close'] - min_down) / df['Close'] < -0.015)

    missed_call = df[(df['RSI'] > 70) & (df['MACDh'] > 0.5) & large_up]
    missed_put = df[(df['RSI'] < 30) & (df['MACDh'] < -0.5) & large_down]

    if not missed_call.empty:
        report.append(f"⚠️ 检测到 {len(missed_call)} 个可能未捕捉的上涨波段。建议审查 Call 入场条件，如 RSI 放宽至 60-65，MACDh 阈值放松至 0.3。")

    if not missed_put.empty:
        report.append(f"⚠️ 检测到 {len(missed_put)} 个可能未捕捉的下跌波段。建议审查 Put 入场条件，如 RSI 提高至 35-40，MACDh 放宽至 -0.3。")

    if len(report) == 0:
        report.append("✅ 今日无明显错失信号，当前策略表现稳定。")

    return report

# -------- Save Report --------
def save_report(lines):
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"🧠 策略诊断报告 - {datetime.now(tz=EST).strftime('%Y-%m-%d')}\n\n")
        for line in lines:
            f.write(line + "\n")
    print(f"📄 报告生成完成：{REPORT_FILE}")

# -------- Main --------
def main():
    try:
        df = get_today_data()
        df = compute_indicators(df)
        report = analyze_missed_signals(df)
        save_report(report)
    except Exception as e:
        print("[错误] 分析失败：", e)

if __name__ == "__main__":
    main()
