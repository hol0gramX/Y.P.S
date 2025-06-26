import os
import json
import requests

# 使用主脚本中同样的 Gist 参数
GIST_ID = "7490de39ccc4e20445ef576832bea34b"
GIST_FILENAME = "last_signal.json"
GIST_TOKEN = os.environ.get("GIST_TOKEN")

def load_last_signal():
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        r = requests.get(url, headers=headers)
        content = r.json()["files"][GIST_FILENAME]["content"]
        return json.loads(content)
    except Exception as e:
        print("❌ 读取失败:", e)
        return {"position": "none"}

def save_last_signal(state):
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(state)
            }
        }
    }
    try:
        r = requests.patch(url, headers=headers, json=data)
        print("✅ 保存成功:", state, "| 状态码:", r.status_code)
    except Exception as e:
        print("❌ 保存失败:", e)

if __name__ == "__main__":
    print("🔍 当前状态:", load_last_signal())
    new_state = {"position": "call"}
    print("💾 保存状态为:", new_state)
    save_last_signal(new_state)
    print("🔁 重新读取:", load_last_signal())
