#!/bin/bash
# Federated Learning Hospital Node Launcher for Linux / Mac

echo "======================================================="
echo "    🏥 FEDERATED LEARNING HOSPITAL NODE LAUNCHER"
echo "======================================================="
echo ""

# Check python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found. Please install Python 3.9+."
    exit 1
fi

# Check certs
if [ ! -d "certs" ]; then
    echo "[ERROR] 'certs' directory missing. Please extract your onboarding kit."
    exit 1
fi

# Start node
echo "🚀 Starting Hospital Node..."
python3 client.py
