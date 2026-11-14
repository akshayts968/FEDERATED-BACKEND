@echo off
title Federated Learning Hospital Node
color 0A

echo =======================================================
echo     🏥 FEDERATED LEARNING HOSPITAL NODE LAUNCHER
echo =======================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.9+ from python.org.
    pause
    exit /b 1
)

:: 2. Check virtual environment or dependencies
if not exist "certs" (
    echo [ERROR] 'certs' folder missing! Please extract all files from your Onboarding Kit ZIP.
    pause
    exit /b 1
)

:: 3. Check for .env file
if not exist ".env" (
    echo [WARNING] .env file not found. Creating default .env...
    echo HOSPITAL_NAME=hospital_node > .env
    echo SERVER_URL=https://your-server-domain.com >> .env
    echo PORT=5001 >> .env
    echo DATA_PATH=./data/Train >> .env
    echo Please review and edit .env with your assigned hospital credentials.
)

:: 4. Start the Node (All flags defaulted)
echo.
echo 🚀 Starting Hospital Node...
echo [INFO] Training data path: ./data/Train
echo [INFO] Close this window anytime to stop participating.
echo.

:: Auto-detect virtual environment if present
if exist "..\venv\Scripts\python.exe" (
    set "PY_CMD=..\venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

%PY_CMD% client.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Node stopped with error.
    pause
)
