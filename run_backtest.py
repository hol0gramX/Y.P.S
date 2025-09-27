import sys
import subprocess
import platform

print("=== Python / pip info ===")
print("Python:", sys.version)
subprocess.run([sys.executable, "-m", "pip", "--version"])

packages = [
    ("numpy", ">=1.23"),
    ("pandas", ">=1.3"),
    ("pandas_market_calendars", ""),
    ("pandas_ta", ">=0.3.21.0"),  # Python 3.11 可用
    ("yfinance", ""),
    ("requests", "")
]

print("\n=== Checking available versions ===")
for pkg, ver in packages:
    try:
        print(f"\nPackage: {pkg}{ver}")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg+ver], check=True)
        subprocess.run([sys.executable, "-m", "pip", "show", pkg])
    except subprocess.CalledProcessError:
        print(f"⚠️ Failed to install {pkg}")

print("\n=== Running spy_backtest_date.py ===")
try:
    subprocess.run([sys.executable, "spy_backtest_date.py"], check=True)
except subprocess.CalledProcessError:
    print("❌ Backtest failed!")
