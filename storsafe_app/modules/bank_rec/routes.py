"""
Bank Reconciliation Routes.

Placeholder - will be populated during migration from existing Bank Rec app.
"""

from flask import render_template, redirect, url_for

from . import bp


@bp.route("/")
def dashboard():
    """Bank Reconciliation dashboard - list of periods."""
    # Placeholder - full implementation will be migrated
    return render_template("bank_rec/dashboard.html")


@bp.route("/upload")
def upload():
    """Upload page for bank statements and Yardi files."""
    # Placeholder - full implementation will be migrated
    return render_template("bank_rec/upload.html")


@bp.route("/period/<int:period_id>")
def period_detail(period_id: int):
    """Detail view for a specific reconciliation period."""
    # Placeholder - full implementation will be migrated
    return render_template("bank_rec/period_detail.html", period_id=period_id)
