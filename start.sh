#!/bin/bash
# Startup script to run Flask and Celery together

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

echo "Starting Redis..."
redis-server --daemonize yes

echo "Waiting for Redis to start..."
sleep 2

echo "Starting Celery worker in background..."
celery -A tasks worker --loglevel=info --pool=solo &

echo "Waiting for Celery to initialize..."
sleep 3

echo "Starting Flask application..."
python main.py
