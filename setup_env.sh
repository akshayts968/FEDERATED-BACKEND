#!/bin/bash
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt
echo "📁 Creating folder structure..."
mkdir -p data/Train certs
echo "✅ Setup Complete! Place images in data/Train and run client.py"