def generate_signals(df):
    signals = []
    last_signal_time = None
    in_position = None

    for i in range(5, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row.name
        tstr = ts.strftime("%Y-%m-%d %H:%M:%S")
        current_time = ts.time()

        if not is_market_day(ts):
            continue

        if current_time >= REGULAR_END and in_position is not None:
            signals.append(f"[{tstr}] 🛑 市场收盘，清空仓位")
            in_position = None
            continue

        if current_time < REGULAR_START or current_time >= REGULAR_END:
            continue

        if last_signal_time == row.name:
            continue

        rsi = row["RSI"]
        macd = row["MACD"]
        macdh = row["MACDh"]
        slope = calculate_rsi_slope(df.iloc[i - 5:i + 1]).iloc[-1]
        strength = "强" if abs(slope) > 0.25 else "中" if abs(slope) > 0.15 else "弱"

        # === 出场 + 反手 ===
        if in_position == "CALL" and rsi < 50 and slope < 0 and macd < 0.05 and macdh < 0.05:
            signals.append(f"[{tstr}] ⚠️ Call 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name

            # 🔁 加入 VWAP 反手 PUT 条件
            if (
                (rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0)
                or allow_top_rebound_put(row, prev)
                or (row["Close"] < row["VWAP"] and prev["Close"] > prev["VWAP"] and slope < -0.1 and macdh < 0)
            ):
                signals.append(f"[{tstr}] 📉 反手 Put：Call 结构破坏 + Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            continue

        elif in_position == "PUT" and rsi > 50 and slope > 0 and macd > -0.05 and macdh > -0.05:
            signals.append(f"[{tstr}] ⚠️ Put 出场信号（趋势：转弱）")
            in_position = None
            last_signal_time = row.name

            # 🔁 加入 VWAP 反手 CALL 条件
            if (
                (rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0)
                or allow_bottom_rebound_call(row, prev)
                or (row["Close"] > row["VWAP"] and prev["Close"] < prev["VWAP"] and slope > 0.1 and macdh > 0)
            ):
                signals.append(f"[{tstr}] 📈 反手 Call：Put 结构破坏 + Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            continue

        # === 入场（含回补） ===
        if in_position is None:
            if rsi > 53 and slope > 0.15 and macd > 0 and macdh > 0:
                signals.append(f"[{tstr}] 📈 主升浪 Call 入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            elif rsi < 47 and slope < -0.15 and macd < 0 and macdh < 0:
                signals.append(f"[{tstr}] 📉 主跌浪 Put 入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name
            elif allow_bottom_rebound_call(row, prev) or allow_bollinger_rebound(row, prev, "CALL"):
                signals.append(f"[{tstr}] 📈 底部反弹 Call 捕捉（评分：4/5）")
                in_position = "CALL"
                last_signal_time = row.name
            elif allow_top_rebound_put(row, prev) or allow_bollinger_rebound(row, prev, "PUT"):
                signals.append(f"[{tstr}] 📉 顶部反转 Put 捕捉（评分：3/5）")
                in_position = "PUT"
                last_signal_time = row.name
            elif allow_call_reentry(row, prev):
                signals.append(f"[{tstr}] 📈 趋势回补 Call 再入场（{strength}）")
                in_position = "CALL"
                last_signal_time = row.name
            elif allow_put_reentry(row, prev):
                signals.append(f"[{tstr}] 📉 趋势回补 Put 再入场（{strength}）")
                in_position = "PUT"
                last_signal_time = row.name

    return signals




