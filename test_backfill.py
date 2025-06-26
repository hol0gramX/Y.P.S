import pandas as pd
from datetime import date
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

def get_market_open_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty:
        return None, None
    return sch.iloc[0]['market_open'].tz_convert(EST), sch.iloc[0]['market_close'].tz_convert(EST)

def is_early_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty:
        return False
    norm = pd.Timestamp.combine(d, pd.Timestamp("16:00").time()).tz_localize(EST)
    return sch.iloc[0]['market_close'].tz_convert(EST) < norm

def main():
    # 2025年7月3日
    d = date(2025, 7, 3)
    op, cl = get_market_open_close(d)
    early = is_early_close(d)
    print(f"日期: {d}, 开盘时间: {op}, 收盘时间: {cl}, 是否早收: {early}")

    # 2025年7月4日 独立日 放假
    d2 = date(2025, 7, 4)
    op2, cl2 = get_market_open_close(d2)
    print(f"日期: {d2}, 开盘时间: {op2}, 收盘时间: {cl2} (应无交易)")

    # 2025年7月5日 周六
    d3 = date(2025, 7, 5)
    op3, cl3 = get_market_open_close(d3)
    print(f"日期: {d3}, 开盘时间: {op3}, 收盘时间: {cl3} (周末应无交易)")

    # 2025年7月6日 周日
    d4 = date(2025, 7, 6)
    op4, cl4 = get_market_open_close(d4)
    print(f"日期: {d4}, 开盘时间: {op4}, 收盘时间: {cl4} (周末应无交易)")

    # 2025年7月7日 周一
    d5 = date(2025, 7, 7)
    op5, cl5 = get_market_open_close(d5)
    print(f"日期: {d5}, 开盘时间: {op5}, 收盘时间: {cl5} (正常交易日)")

if __name__ == "__main__":
    main()
