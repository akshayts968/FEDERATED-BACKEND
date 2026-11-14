@echo off
title Federated Learning - One-Click Any-Time Training
color 0B

echo =======================================================
echo     🧠 FEDERATED LEARNING: START TRAINING NOW
echo =======================================================
echo.
echo [1/4] Checking Python environment...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo [2/4] Verifying security certificates...
if not exist "certs" (
    echo [ERROR] 'certs' folder missing! Please extract all files from your Onboarding Kit ZIP.
    pause
    exit /b 1
)

echo [3/4] Checking local MRI dataset folder...
if not exist "data\Train" (
    mkdir "data\Train"
    echo [NOTICE] Created data\Train folder. Place your MRI class subfolders inside data\Train!
)

echo [4/4] Connecting to Cloud Aggregator & Initiating Training...
echo.
echo 🔄 Pulling global model, training on private MRI scans, and submitting update...
echo.

python client.py --train-now

echo.
echo =======================================================
if %errorlevel% equ 0 (
    echo  ✅ Training and model update completed successfully!
) else (
    echo  ❌ Training stopped with an error. Check logs above.
)
echo =======================================================
echo.
pause
