"""
Configuration for Bank Reconciliation Web App
"""

import os
from pathlib import Path


class Config:
    """Base configuration."""
    
    # Paths
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    DATABASE_PATH = DATA_DIR / "bank_rec.db"
    UPLOAD_FOLDER = DATA_DIR / "uploads"
    
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls"}
    
    @classmethod
    def init_app(cls, app):
        """Initialize app with this configuration."""
        # Ensure directories exist
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.UPLOAD_FOLDER.mkdir(exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False


# Configuration mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
