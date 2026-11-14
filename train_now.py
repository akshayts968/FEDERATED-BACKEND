import os
import sys
import subprocess

# Auto-detect and use venv python if present
venv_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "venv", "Scripts", "python.exe")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "venv", "Scripts", "python.exe")),
    r"C:\Users\HP\AKSHAY\Federated\venv\Scripts\python.exe"
]

python_exe = sys.executable
for candidate in venv_candidates:
    if os.path.exists(candidate):
        python_exe = candidate
        break

print("=" * 55)
print("    🧠 FEDERATED LEARNING: START TRAINING NOW")
print("=" * 55)
print(f"🐍 Python Interpreter: {python_exe}\n")

# 1. Check for certs folder
if not os.path.exists("certs"):
    print("❌ [ERROR] 'certs' folder missing! Please extract all files from your Onboarding Kit ZIP.")
    input("\nPress Enter to exit...")
    sys.exit(1)

# 2. Check for data folder
if not os.path.exists("data/Train"):
    os.makedirs("data/Train", exist_ok=True)
    print("📁 [NOTICE] Created data/Train folder. Please place your MRI class folders inside data/Train!")

# 3. Launch training
print("🔄 Connecting to Cloud Aggregator & Initiating Training...")
print("📡 Pulling global model, training on private MRI scans, and submitting update...\n")

try:
    ret = subprocess.run([python_exe, "client.py", "--train-now"])
    print("\n" + "=" * 55)
    if ret.returncode == 0:
        print("  ✅ Training and model update completed successfully!")
    else:
        print("  ❌ Training stopped with an error.")
    print("=" * 55)
except Exception as e:
    print(f"❌ Execution error: {e}")

input("\nPress Enter to close this window...")
