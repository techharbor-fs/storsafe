"""
API Routes for Storsafe Dashboard.
"""

from flask import jsonify, request

from . import api_bp
from ..db import get_db_service


@api_bp.route("/db/init", methods=["POST"])
def init_database():
    """Initialize database tables."""
    db_service = get_db_service()
    result = db_service.init_db()
    
    if result["status"] == "success":
        return jsonify(result), 200
    return jsonify(result), 500


@api_bp.route("/db/status", methods=["GET"])
def database_status():
    """Get database connection status and record counts."""
    db_service = get_db_service()
    result = db_service.get_status()
    
    if result["status"] == "connected":
        return jsonify(result), 200
    return jsonify(result), 500


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Railway."""
    return jsonify({
        "status": "healthy",
        "app": "storsafe-dashboard",
    }), 200
