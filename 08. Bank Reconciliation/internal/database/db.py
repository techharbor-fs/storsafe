"""
Database connection and initialization.

Provides SQLite database access for the Flask application.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from flask import Flask, g, current_app


class Database:
    """Database manager for the application."""
    
    def __init__(self):
        self.app: Optional[Flask] = None
    
    def init_app(self, app: Flask):
        """Initialize database with Flask app.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        
        # Register teardown
        app.teardown_appcontext(self._teardown)
        
        # Initialize database on first request
        with app.app_context():
            self._init_db()
    
    def _teardown(self, exception):
        """Close database connection at end of request."""
        db = g.pop("db", None)
        if db is not None:
            db.close()
    
    def _init_db(self):
        """Initialize database schema."""
        db_path = current_app.config["DATABASE_PATH"]
        
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read and execute schema
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, "r") as f:
            schema = f.read()
        
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema)
        conn.commit()
        conn.close()
        
        current_app.logger.info(f"Database initialized at {db_path}")
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection for current request.
        
        Returns:
            SQLite connection with Row factory
        """
        if "db" not in g:
            db_path = current_app.config["DATABASE_PATH"]
            g.db = sqlite3.connect(str(db_path))
            g.db.row_factory = sqlite3.Row
            # Enable foreign keys
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db


# Singleton instance
db = Database()


def get_db() -> sqlite3.Connection:
    """Get database connection.
    
    Returns:
        SQLite connection with Row factory
    """
    return db.get_connection()


def close_db(exception=None):
    """Close database connection."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Initialize database schema (for CLI use)."""
    db._init_db()
