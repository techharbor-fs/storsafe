"""
API Routes for Storsafe Dashboard.

Provides REST endpoints for:
- Database management
- File operations (Google Drive)
- Module-specific APIs
"""

from flask import Blueprint

api_bp = Blueprint("api", __name__)

from . import routes
