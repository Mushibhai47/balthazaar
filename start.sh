#!/bin/bash
# Startup script to run Flask and Celery together

echo "Starting Redis..."
redis-server --daemonize yes

echo "Waiting for Redis to start..."
sleep 2

echo "Starting Celery worker in background..."
celery -A tasks worker --loglevel=info --pool=solo &

echo "Waiting for Celery to initialize..."
sleep 3

echo "Starting Flask application..."
python3 main.py
