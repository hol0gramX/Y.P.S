import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pandas_ta as ta
import pandas_market_calendars as mcal

# ========= 配置 =========
SYMBOL = "SPY"
STATE_FILE = os.path.abspath("last_signal.json")
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# ========= 时间相关 =========
def get_est_now():
    return datetime.now(tz=EST)

def get_trading_days(start, end):
    return nasdaq.schedule(start_date=start, end_date=end).index.tz_localize(None)

def get_market_open_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    if sch.empty: return None, None
    return sch.iloc[0]['market_open'].tz_convert(EST), sch.iloc[0]['market_close'].tz_convert(EST)

def is_early_close(d):
    sch = nasdaq.schedule(start_date=d, end_date=d)
    return not sch.empty and sch.iloc[0]['market_close'].tz_convert(EST).hour < 16

# ========= 技术指标 =========
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

# ========= 趋势判断（5min） =========
def get_latest_5min_trend(df_5min, ts):
    try:
        subset = df_5min[df_5min.index <= ts]
        recent = subset[subset.index >= ts - timedelta(hours=2)]

        if recent.empty or len(recent) < 20:
            return None

        ma20 = recent['Close'].rolling(20).mean()
        if pd.isna(ma20.iloc[-1]):
            return None

        latest_close = recent.iloc[-1]['Close']
        latest_ma20 = ma20.iloc[-1]

        if latest_close > latest_ma20:
            return {"trend": "📈上涨"}
        elif latest_close < latest_ma20:
            return {"trend": "📉下跌"}
        else:
            return {"trend": "⚖️震荡"}

    except Exception as e:
        print(f"[5min趋势判断失败] {e}")
        return None



# ========= 数据加载 =========
def get_data():
    now = get_est_now()
    today = now.date()
    trade_days = get_trading_days(today - timedelta(days=14), today)
    trade_days = trade_days[trade_days <= pd.Timestamp(today)]
    recent = trade_days[-3:]

    sessions = []
    for d in recent:
        op, cl = get_market_open_close(d.date())
        early = is_early_close(d.date())
        sessions.append((op, cl, early))

    start_dt = sessions[0][0]
    end_dt = sessions[-1][1] + timedelta(seconds=1)

    print(f"[DEBUG] 下载数据：{start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    df = yf.download(SYMBOL, interval="1m", start=start_dt.tz_convert('UTC'), end=end_dt.tz_convert('UTC'),
                     progress=False, prepost=True, auto_adjust=True)
    if df.empty: raise ValueError("下载失败或数据为空")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['High', 'Low', 'Close', 'Volume'])
    df = df[df['Volume'] > 0]
    df.index = df.index.tz_convert(EST) if df.index.tz is not None else df.index.tz_localize('UTC').tz_convert(EST)

    mask = pd.Series(False, index=df.index)
    for op, cl, early in sessions:
        intervals = [(op - timedelta(hours=5, minutes=30), op), (op, cl)]
        if not early:
            pm_start, pm_end = cl, cl + timedelta(hours=4)
            intervals.append((pm_start, pm_end))
        for s, e in intervals:
            mask |= (df.index >= s) & (df.index < e)

    df = df[mask]
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    df = compute_macd(df)
    df.ffill(inplace=True)
    return df.dropna()

# ========= 信号逻辑 =========
def strong_volume(row): return row['Volume'] >= row['Vol_MA5']

def determine_strength(row, direction):
    if direction == "call":
        if row['RSI'] > 65 and row['MACDh'] > 0.5: return "强"
        elif row['RSI'] < 55: return "弱"
    elif direction == "put":
        if row['RSI'] < 35 and row['MACDh'] < -0.5: return "强"
        elif row['RSI'] > 45: return "弱"
    return "中"

def check_call_entry(row): return row['Close'] > row['VWAP'] and row['RSI'] > 50 and row['MACDh'] > -0.1 and strong_volume(row)
def check_put_entry(row): return row['Close'] < row['VWAP'] and row['RSI'] < 51 and row['MACDh'] < 0.15 and strong_volume(row)
def check_call_exit(row): return row['RSI'] < 48 and strong_volume(row)
def check_put_exit(row): return row['RSI'] > 52 and strong_volume(row)

def load_last_signal():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {"position": "none"}

def save_last_signal(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

# ========= 主回测流程 =========
def main():
    print(f"[🔁 回测开始] {get_est_now().isoformat()}")
    try:
        df = get_data()
        df_5min = yf.download(SYMBOL, interval='5m', period='2d', progress=False, auto_adjust=True)
        if df_5min.empty:
            raise ValueError("5分钟数据为空，无法判断趋势")
        df_5min.index = df_5min.index.tz_localize("UTC").tz_convert(EST) if df_5min.index.tz is None else df_5min.index.tz_convert(EST)

        state = load_last_signal()
        signals = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            time_est = row.name
            signal = None

            trend_info = get_latest_5min_trend(df_5min, time_est)
            trend_label = f"{trend_info['trend']}（5min）" if trend_info else "未知"

            if state["position"] == "call" and check_call_exit(row):
                state["position"] = "none"
                if check_put_entry(row):
                    strength = determine_strength(row, "put")
                    state["position"] = "put"
                    signal = f"🔁 反手 Put：Call 结构破坏 + Put 入场（{strength}，趋势：{trend_label}）"
                else:
                    signal = f"⚠️ Call 出场信号（趋势：{trend_label}）"

            elif state["position"] == "put" and check_put_exit(row):
                state["position"] = "none"
                if check_call_entry(row):
                    strength = determine_strength(row, "call")
                    state["position"] = "call"
                    signal = f"🔁 反手 Call：Put 结构破坏 + Call 入场（{strength}，趋势：{trend_label}）"
                else:
                    signal = f"⚠️ Put 出场信号（趋势：{trend_label}）"

            elif state["position"] == "none":
                if check_call_entry(row):
                    strength = determine_strength(row, "call")
                    state["position"] = "call"
                    signal = f"📈 主升浪 Call 入场（{strength}，趋势：{trend_label}）"
                elif check_put_entry(row):
                    strength = determine_strength(row, "put")
                    state["position"] = "put"
                    signal = f"📉 主跌浪 Put 入场（{strength}，趋势：{trend_label}）"

            if signal:
                signals.append(f"[{time_est.strftime('%Y-%m-%d %H:%M:%S')}] {signal}")
                save_last_signal(state)

        if not signals:
            print("[信息] 今日无信号生成")
        else:
            print("\n".join(signals))

    except Exception as e:
        print(f"[❌ 回测失败] {e}")

if __name__ == "__main__":
    main()


