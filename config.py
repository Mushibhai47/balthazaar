import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "balthazaar-dev-key-change-in-prod")
    SQLALCHEMY_DATABASE_URI = "sqlite:///balthazaar.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
