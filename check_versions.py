import subprocess

# 定义三种方案及其核心包依赖
options = {
    "方案1_Py311_remake": [
        "numpy==1.23.5",
        "pandas==2.3.2",
        "yfinance==0.2.66",
        "requests==2.32.5",
        "pandas_market_calendars==5.1.1",
        "pandas-ta-remake"
    ],
    "方案2_Py310_original": [
        "numpy==1.23.5",
        "pandas==2.3.2",
        "yfinance==0.2.66",
        "requests==2.32.5",
        "pandas_market_calendars==5.1.1",
        "pandas_ta==0.3.20b0"
    ],
    "方案3_Py312_remake_latest": [
        "numpy",
        "pandas",
        "yfinance",
        "requests",
        "pandas_market_calendars",
        "pandas-ta-remake"
    ]
}

def check_versions(packages):
    for pkg in packages:
        print(f"\n--- Checking versions for {pkg} ---")
        try:
            result = subprocess.run(
                ["python", "-m", "pip", "index", "versions", pkg],
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
        except Exception as e:
            print("Error:", e)

# 遍历三种方案
for name, pkgs in options.items():
    print(f"\n=== Testing {name} ===")
    check_versions(pkgs)

