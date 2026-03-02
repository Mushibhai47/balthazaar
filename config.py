import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "balthazaar-dev-key-change-in-prod")
    SQLALCHEMY_DATABASE_URI = "sqlite:///balthazaar.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Celery configuration
    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TIMEZONE = "UTC"
    CELERY_ENABLE_UTC = True

    # Encryption key for API credentials (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "placeholder-generate-real-key-before-production")
