"""
Database layer for Storsafe Dashboard.

Supports dual-mode: SQLite for local development, PostgreSQL for Railway.
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_app(app):
    """Initialize database with Flask app."""
    db.init_app(app)
    
    with app.app_context():
        # Import models to register them
        from . import models
        
        # Create tables if they don't exist
        db.create_all()
        
        # Seed default data
        from .database_service import get_db_service
        db_service = get_db_service()
        db_service.init_app(app)


# Lazy imports to avoid circular dependencies
def get_db_service():
    """Get the database service singleton."""
    from .database_service import get_db_service as _get_db_service
    return _get_db_service()
