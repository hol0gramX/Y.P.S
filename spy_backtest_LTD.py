import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# ========= 配置区域 =========
SYMBOL = "SPY"
EST = ZoneInfo("America/New_York")
START_DATE = (datetime.now(tz=EST) - timedelta(days=2)).strftime("%Y-%m-%d")
END_DATE = datetime.now(tz=EST).strftime("%Y-%m-%d")

# ========= 主逻辑 =========
def main():
    df = yf.download(SYMBOL, start=START_DATE, end=END_DATE, interval="1m", prepost=True)

    # 🧠 确保索引为美东时间（避免 tz_localize 错误）
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(EST)
    else:
        df.index = df.index.tz_convert(EST)

    # ✅ 修复列名 MultiIndex 问题
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    # ✅ 计算技术指标
    df.ta.rsi(length=14, append=True)
    df.ta.macd(append=True)
    df["sma_20"] = df["close"].rolling(20).mean()

    # ✅ 回测主循环
    position = None
    for i in range(len(df)):
        row = df.iloc[i]
        current_time = row.name

        # 开盘前清空持仓（例如盘前 4:00 - 9:30）
        if current_time.time() < time(9, 30):
            if position:
                print(f"[平仓] {current_time.strftime('%H:%M')} 盘前清空持仓：{position}")
                position = None
            continue

        # 判断入场信号（示例逻辑，可替换为主策略）
        if position is None:
            if row["rsi_14"] < 30 and row["macdh_12_26_9"] > 0 and row["close"] > row["sma_20"]:
                position = "CALL"
                print(f"[入场 - CALL 强] {current_time.strftime('%H:%M')} RSI: {row['rsi_14']:.1f}, MACDh: {row['macdh_12_26_9']:.3f}")
            elif row["rsi_14"] > 70 and row["macdh_12_26_9"] < 0 and row["close"] < row["sma_20"]:
                position = "PUT"
                print(f"[入场 - PUT 强] {current_time.strftime('%H:%M')} RSI: {row['rsi_14']:.1f}, MACDh: {row['macdh_12_26_9']:.3f}")

        # 示例出场（可自定义）
        elif position == "CALL" and row["rsi_14"] > 65:
            print(f"[出场 - CALL] {current_time.strftime('%H:%M')} RSI: {row['rsi_14']:.1f}")
            position = None
        elif position == "PUT" and row["rsi_14"] < 35:
            print(f"[出场 - PUT] {current_time.strftime('%H:%M')} RSI: {row['rsi_14']:.1f}")
            position = None

if __name__ == "__main__":
    main()

