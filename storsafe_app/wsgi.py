"""
WSGI entry point for Railway deployment.

When deployed to Railway with storsafe_app as root directory,
this file is at /app/wsgi.py and imports are local (not package-based).
"""

import os
import sys

# Determine if we're running as a package (local dev) or standalone (Railway)
# On Railway: /app/wsgi.py with files like /app/app.py, /app/config.py
# Locally: running from parent folder as storsafe_app.wsgi
current_dir = os.path.dirname(os.path.abspath(__file__))

# Try package import first (local development), fall back to local import (Railway)
try:
    from storsafe_app.app import create_app
except ImportError:
    # Running on Railway - add current dir to path for local imports
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    from app import create_app

# Create the app instance for gunicorn
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
