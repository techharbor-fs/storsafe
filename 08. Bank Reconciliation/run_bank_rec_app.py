#!/usr/bin/env python3
"""
Bank Reconciliation Web Application

Entry point for the Flask web application.
Provides a web interface for bank reconciliation workflow.

Usage:
    python run_bank_rec_app.py
    
    Then open http://localhost:5000 in your browser.
"""

import sys
from pathlib import Path

# Add internal to path for imports
sys.path.insert(0, str(Path(__file__).parent / "internal"))

from internal.app import create_app


def main():
    """Run the Flask development server."""
    app = create_app()
    
    print("=" * 60)
    print("Bank Reconciliation Web App")
    print("=" * 60)
    print()
    print("Starting server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print()
    
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )


if __name__ == "__main__":
    main()
