import os
import sys
import subprocess

print("=" * 55)
print("    🧠 FEDERATED LEARNING: START TRAINING NOW")
print("=" * 55)
print()

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
    ret = subprocess.run([sys.executable, "client.py", "--train-now"])
    print("\n" + "=" * 55)
    if ret.returncode == 0:
        print("  ✅ Training and model update completed successfully!")
    else:
        print("  ❌ Training stopped with an error.")
    print("=" * 55)
except Exception as e:
    print(f"❌ Execution error: {e}")

input("\nPress Enter to close this window...")
