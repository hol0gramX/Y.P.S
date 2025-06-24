import requests

DISCORD_WEBHOOK_URL = "xxx"

resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": "这是测试消息，确认Webhook正常"})
print(f"Discord 返回状态码: {resp.status_code}")

if resp.status_code == 204:
    print("消息发送成功")
else:
    print("消息发送失败:", resp.text)
