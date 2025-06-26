import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

SYMBOL = "SPY"

def troubleshoot():
    est = ZoneInfo("America/New_York")

    df = yf.download(
        SYMBOL,
        interval="1m",
        start="2025-06-24",
        end="2025-06-26",
        progress=False,
        prepost=True,
        auto_adjust=True
    )

    print("=== 原始数据列名（含MultiIndex） ===")
    print(df.columns)

    # 如果是MultiIndex，把列名扁平化
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        print("=== 扁平化后列名 ===")
        print(df.columns)

    print(f"数据总行数：{len(df)}")

    needed_cols = ['High', 'Low', 'Close', 'Volume']
    missing_cols = [col for col in needed_cols if col not in df.columns]
    if missing_cols:
        print(f"缺少必要列：{missing_cols}")
        return

    # 查看有多少行含缺失数据
    nan_rows = df[df[needed_cols].isna().any(axis=1)]
    print(f"含缺失值行数: {len(nan_rows)}")

    # 清理缺失数据
    df_clean = df.dropna(subset=needed_cols)
    print(f"清理缺失后行数: {len(df_clean)}")

    # 时区处理
    if df_clean.index.tz is None:
        df_clean.index = df_clean.index.tz_localize('UTC').tz_convert(est)
    else:
        df_clean.index = df_clean.index.tz_convert(est)

    print("前5行数据示例：")
    print(df_clean.head())

if __name__ == "__main__":
    troubleshoot()


