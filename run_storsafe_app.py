#!/usr/bin/env python3
"""
Storsafe Dashboard - Launcher

Starts the unified web application for local development.
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storsafe_app.app import create_app

if __name__ == "__main__":
    app = create_app("development")
    port = int(os.environ.get("PORT", 5000))
    
    print(f"\n{'='*60}")
    print("STORSAFE DASHBOARD")
    print(f"{'='*60}")
    print(f"Starting development server on http://localhost:{port}")
    print(f"Database: SQLite (local development mode)")
    print(f"{'='*60}\n")
    
    app.run(host="0.0.0.0", port=port, debug=True)
