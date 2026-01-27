"""
Storsafe Dashboard - Flask Application Factory

Creates and configures the unified Flask application for all Storsafe workflows.
"""

import os
from flask import Flask, redirect, url_for

from .config import config


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application.
    
    Args:
        config_name: Configuration to use ('development', 'production', 'testing', or 'default')
        
    Returns:
        Configured Flask application
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")
    
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Store database URL in app config
    app.config["SQLALCHEMY_DATABASE_URI"] = config[config_name].get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize database
    from .db import db
    db.init_app(app)
    
    # Create tables within app context
    with app.app_context():
        # Import models to register them with SQLAlchemy
        from .db import models  # noqa: F401
        db.create_all()
    
    # Register module blueprints
    from .modules.bank_rec import bp as bank_rec_bp
    app.register_blueprint(bank_rec_bp)
    
    # Register API routes
    from .api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    
    # Root redirect to dashboard
    @app.route("/")
    def index():
        return redirect(url_for("bank_rec.dashboard"))
    
    # Health check endpoint for Railway
    @app.route("/health")
    def health():
        return {"status": "healthy", "app": "storsafe-dashboard"}
    
    return app


# Entry point for running directly (Railway uses this)
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
