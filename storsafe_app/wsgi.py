"""
WSGI entry point for Railway deployment.

This file handles the import path setup so the app can be run
either as a module or directly via gunicorn/python.
"""

import os
import sys

# Ensure the parent directory is in the path
# This allows imports like `from storsafe_app.config import config`
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now we can import using absolute paths
from storsafe_app.app import create_app

# Create the app instance for gunicorn
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
