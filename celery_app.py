"""
Celery application instance for background task processing
"""
from celery import Celery
from config import Config
from flask import Flask
from database.models import db

# Initialize Flask app for Celery tasks
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Initialize Celery
celery = Celery(
    "balthazaar",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND
)

# Configure Celery with Flask config
celery.conf.update(
    task_serializer=Config.CELERY_TASK_SERIALIZER,
    result_serializer=Config.CELERY_RESULT_SERIALIZER,
    accept_content=Config.CELERY_ACCEPT_CONTENT,
    timezone=Config.CELERY_TIMEZONE,
    enable_utc=Config.CELERY_ENABLE_UTC,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minute soft limit
)
