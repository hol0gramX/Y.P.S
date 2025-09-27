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
    subprocess.run(["python", "-m", "pip", "index", "versions", pkg])
