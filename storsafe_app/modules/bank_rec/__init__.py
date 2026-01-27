"""
Bank Reconciliation Module.

Handles bank statement reconciliation with Yardi data.
"""

from flask import Blueprint

bp = Blueprint(
    "bank_rec",
    __name__,
    url_prefix="/bank-rec",
    template_folder="templates",
)

from . import routes
