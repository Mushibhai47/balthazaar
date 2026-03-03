"""
Flask application factory for use by both main.py and celery_app.py
"""
from flask import Flask
from database.models import db
from config import Config

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize database
    db.init_app(app)

    return app
