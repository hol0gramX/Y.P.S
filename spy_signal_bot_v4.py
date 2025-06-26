import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas_ta as ta
import pandas_market_calendars as mcal

# --------- Gist 配置 ---------
GIST_ID = "7490de39ccc4e20445ef576832bea34b"
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")

# --------- 常规变量 ---------
SYMBOL = "SPY"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
EST = ZoneInfo("America/New_York")
nasdaq = mcal.get_calendar("NASDAQ")

# --------- Gist 状态管理 ---------
def load_last_signal_from_gist():
    if not GIST_TOKEN:
        print("[DEBUG] GIST_TOKEN 未设置，返回默认状态")
        return {"position": "none"}
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        content = r.json()["files"][GIST_FILENAME]["content"]
        state = json.loads(content)
        print(f"[DEBUG] 从 Gist 读取持仓状态: {state}")
        return state
    except Exception as e:
        print(f"[DEBUG] 读取 Gist 状态失败: {e}")
        return {"position": "none"}

def save_last_signal(state):
    if not GIST_TOKEN:
        print("[DEBUG] GIST_TOKEN 未设置，无法保存状态")
        return
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"files": {GIST_FILENAME: {"content": json.dumps(state)}}}
    try:
        response = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)
        print(f"[DEBUG] 保存持仓状态为: {state}")
        print(f"[DEBUG] 保存返回状态码: {response.status_code}")
        if response.status_code != 200:
            print(f"[ERROR] Gist 保存失败内容: {response.text}")
    except Exception as e:
        print(f"[ERROR] 保存状态出错: {e}")

load_last_signal = load_last_signal_from_gist

# 其他部分不变，只在 main() 中补充状态打印

def main():
    print(f"[DEBUG] 当前工作目录: {os.getcwd()}")
    state = load_last_signal()
    print(f"[DEBUG] 程序启动时仓位状态: {state.get('position', 'none')}")
    # 其余 main 内逻辑继续保留，略...

if __name__ == "__main__":
    main()




