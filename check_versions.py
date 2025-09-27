import subprocess

packages = [
    "numpy",
    "pandas",
    "pandas_ta",
    "pandas_market_calendars",
    "yfinance",
    "requests"
]

for pkg in packages:
    print(f"\n=== {pkg} ===")
    try:
        # 使用 capture_output=True 捕获输出，并解码为字符串
        result = subprocess.run(
            ["python", "-m", "pip", "index", "versions", pkg],
            capture_output=True,
            text=True
        )
        print(result.stdout)  # 打印标准输出
        if result.stderr:     # 如果有错误输出也打印
            print("ERROR:", result.stderr)
    except Exception as e:
        print(f"Failed to check {pkg}: {e}")
