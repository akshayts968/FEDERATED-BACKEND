@echo off
echo 🚀 Starting Federated Node Setup...

:: 1. Install dependencies
echo 📦 Installing Python libraries...
pip install -r requirements.txt

:: 2. Create required folder structure
echo 📁 Creating directories...
if not exist "data\Train" mkdir "data\Train"
if not exist "certs" mkdir "certs"
if not exist "model" mkdir "model"

echo.
echo ✅ Environment Ready! 
echo 1. Place your MRI images in: data\Train
echo 2. Your certificates are already in: certs\
echo 3. Configure your .env file.
echo 4. Run: python client.py --port 5001 --data-path ./data/Train
pause