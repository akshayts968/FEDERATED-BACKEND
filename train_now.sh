#!/bin/bash
# One-click Any-Time Training script for Linux / Mac

echo "======================================================="
echo "    🧠 FEDERATED LEARNING: START TRAINING NOW"
echo "======================================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.9+."
    exit 1
fi

if [ ! -d "certs" ]; then
    echo "[ERROR] 'certs' folder missing! Please extract all files from your Onboarding Kit ZIP."
    exit 1
fi

mkdir -p "data/Train"

echo "🔄 Pulling global model, training on private MRI scans, and submitting update..."
python3 client.py --train-now

echo ""
echo "✅ Finished."
