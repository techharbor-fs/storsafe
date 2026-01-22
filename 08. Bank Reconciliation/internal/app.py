"""
Flask Application Factory

Creates and configures the Flask application.
"""

import os
from flask import Flask

from .config import config


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application.
    
    Args:
        config_name: Configuration to use ('development', 'production', or 'default')
        
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
    
    # Initialize database
    from .database import db
    db.init_app(app)
    
    # Register blueprints
    from .routes import dashboard, upload, adjustments
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(adjustments.bp)
    
    # Root redirect
    @app.route("/")
    def index():
        from flask import redirect, url_for
        return redirect(url_for("dashboard.index"))
    
    return app
