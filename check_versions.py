import importlib
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

def check_import_version(pkg_name, import_name=None):
    """尝试 import 并打印已安装版本"""
    import_name = import_name or pkg_name.replace("-", "_")
    try:
        module = importlib.import_module(import_name)
        version = getattr(module, "__version__", "unknown")
        print(f"✔ {import_name} 已安装，版本: {version}")
    except ModuleNotFoundError:
        print(f"✖ {import_name} 未安装")
    except Exception as e:
        print(f"⚠ {import_name} 导入异常: {e}")

def check_pip_versions(pkg_name):
    """使用 pip 查看可用版本"""
    try:
        result = subprocess.run(
            ["python", "-m", "pip", "index", "versions", pkg_name],
            capture_output=True, text=True
        )
        print(result.stdout if result.stdout else result.stderr)
    except Exception as e:
        print(f"⚠ 查询 {pkg_name} pip 版本失败: {e}")

def check_scheme(scheme_name, packages):
    print(f"\n=== 检查方案: {scheme_name} ===")
    for pkg in packages:
        pkg_clean = pkg.split("==")[0]
        print(f"\n--- {pkg} ---")
        check_import_version(pkg_clean)
        check_pip_versions(pkg_clean)

if __name__ == "__main__":
    for name, pkgs in options.items():
        check_scheme(name, pkgs)


