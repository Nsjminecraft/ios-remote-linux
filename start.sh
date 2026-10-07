#!/bin/bash
# Start iOS-remote: tunnels the device and launches the web UI

set -e

cd "$(dirname "$0")"

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies if needed
if ! python3 -c "import pymobiledevice3" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check for ffmpeg (optional, for recording)
if ! command -v ffmpeg &> /dev/null; then
    echo "Warning: ffmpeg not found. Recording feature will not work."
    echo "Install with: sudo apt install ffmpeg (or equivalent for your system)"
fi

echo "Starting iOS-remote..."
echo "1. Start pymobiledevice3 tunnel (run in separate terminal with sudo):"
echo "   sudo /home/intrealer/iOS-remote/venv/bin/pymobiledevice3 remote tunneld"
echo "2. Web UI will be available at: http://localhost:5000"
echo ""

# Start the app
python3 app.py
