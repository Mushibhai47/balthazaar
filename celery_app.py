"""
Celery application instance for background task processing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from config import Config

# Initialize Celery WITHOUT Flask app to avoid integration issues
celery = Celery(
    "balthazaar",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND
)

# Configure Celery
celery.conf.update(
    task_serializer=Config.CELERY_TASK_SERIALIZER,
    result_serializer=Config.CELERY_RESULT_SERIALIZER,
    accept_content=Config.CELERY_ACCEPT_CONTENT,
    timezone=Config.CELERY_TIMEZONE,
    enable_utc=Config.CELERY_ENABLE_UTC,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    beat_schedule={
        'run-scheduled-reports-hourly': {
            'task': 'tasks.run_scheduled_reports',
            'schedule': 3600.0,  # every hour
        },
    },
    broker_connection_retry_on_startup=True,
)

# Import tasks to register them with Celery
import tasks  # noqa: F401
