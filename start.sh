#!/bin/bash
# Startup script

# Set up virtualenv if not exists
if [ ! -d "$HOME/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$HOME/.venv"
fi

# Activate venv
source "$HOME/.venv/bin/activate"

# Install dependencies if needed
echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Starting Flask application..."
python main.py
