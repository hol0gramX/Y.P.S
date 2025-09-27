import subprocess
import sys
import os
from datetime import datetime

# ==== Step 1: 检查并安装依赖 ====
req_file = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
print(f"[1️⃣] 安装依赖：{req_file}")

try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
except subprocess.CalledProcessError as e:
    print(f"[❌] 依赖安装失败: {e}")
    sys.exit(1)

# ==== Step 2: 导入回测脚本 ====
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import spy_backtest_date
except Exception as e:
    print(f"[❌] 导入回测脚本失败: {e}")
    sys.exit(1)

# ==== Step 3: 执行回测 ====
try:
    print(f"[2️⃣] 开始回测: {datetime.now()}")
    spy_backtest_date.backtest("2025-09-03", "2025-09-03")
    print(f"[✅] 回测完成: {datetime.now()}")
except Exception as e:
    print(f"[❌] 回测执行失败: {e}")
    raise
