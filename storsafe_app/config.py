"""
Configuration for Storsafe Dashboard

Supports dual-mode database: SQLite for local development, PostgreSQL for Railway.
"""

import os
import json
from pathlib import Path


class Config:
    """Base configuration."""
    
    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_FOLDER = DATA_DIR / "uploads"
    
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls"}
    
    # Database - determine mode based on environment
    USE_POSTGRESQL = os.environ.get("USE_POSTGRESQL_PRIMARY", "false").lower() == "true"
    DATABASE_URL = os.environ.get("DATABASE_URL")
    LOCAL_DATABASE_URL = os.environ.get("LOCAL_DATABASE_URL", f"sqlite:///{DATA_DIR / 'storsafe.db'}")
    
    # Google APIs
    SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON")
    GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
    GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    
    @classmethod
    def init_app(cls, app):
        """Initialize app with this configuration."""
        # Ensure directories exist
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.UPLOAD_FOLDER.mkdir(exist_ok=True)
    
    @classmethod
    def get_database_url(cls) -> str:
        """Get the appropriate database URL based on environment."""
        if cls.USE_POSTGRESQL and cls.DATABASE_URL:
            # Railway PostgreSQL - fix postgres:// to postgresql://
            url = cls.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        return cls.LOCAL_DATABASE_URL
    
    @classmethod
    def get_google_credentials(cls) -> dict | None:
        """Parse Google service account credentials from environment."""
        if cls.SERVICE_ACCOUNT_JSON:
            try:
                return json.loads(cls.SERVICE_ACCOUNT_JSON)
            except json.JSONDecodeError:
                return None
        return None


class DevelopmentConfig(Config):
    """Development configuration - uses SQLite by default."""
    DEBUG = True
    USE_POSTGRESQL = False


class ProductionConfig(Config):
    """Production configuration - uses PostgreSQL on Railway."""
    DEBUG = False
    USE_POSTGRESQL = True


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    USE_POSTGRESQL = False


# Configuration mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get the appropriate config based on environment."""
    env = os.environ.get("FLASK_ENV", "development")
    return config.get(env, config["default"])
