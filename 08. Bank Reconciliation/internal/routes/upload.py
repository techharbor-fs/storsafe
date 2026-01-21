"""
Upload Routes

File upload handling for bank statements and Yardi Excel files.
"""

import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename

from ..database import get_db

bp = Blueprint("upload", __name__, url_prefix="/upload")


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return (
        "." in filename 
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )


@bp.route("/", methods=["GET"])
def index():
    """Upload page with dropzone."""
    db = get_db()
    
    # Get existing properties for dropdown
    properties = db.execute(
        "SELECT id, name FROM properties ORDER BY name"
    ).fetchall()
    
    # Current month/year as defaults
    now = datetime.now()
    
    return render_template(
        "upload.html",
        properties=properties,
        current_year=now.year,
        current_month=now.month,
        years=list(range(now.year - 2, now.year + 1)),
        months=[
            (1, "January"), (2, "February"), (3, "March"), (4, "April"),
            (5, "May"), (6, "June"), (7, "July"), (8, "August"),
            (9, "September"), (10, "October"), (11, "November"), (12, "December"),
        ],
    )


@bp.route("/", methods=["POST"])
def upload_files():
    """Handle file upload and processing."""
    db = get_db()
    
    # Get form data
    property_name = request.form.get("property_name", "").strip()
    new_property = request.form.get("new_property", "").strip()
    year = request.form.get("year", type=int)
    month = request.form.get("month", type=int)
    
    # Use new property name if provided
    if new_property:
        property_name = new_property
    
    if not property_name:
        flash("Please select or enter a property name.", "error")
        return redirect(url_for("upload.index"))
    
    if not year or not month:
        flash("Please select a year and month.", "error")
        return redirect(url_for("upload.index"))
    
    # Get or create property
    property_row = db.execute(
        "SELECT id FROM properties WHERE name = ?", (property_name,)
    ).fetchone()
    
    if property_row:
        property_id = property_row["id"]
    else:
        cursor = db.execute(
            "INSERT INTO properties (name) VALUES (?)", (property_name,)
        )
        property_id = cursor.lastrowid
    
    # Get or create reconciliation period
    period_row = db.execute(
        "SELECT id FROM reconciliation_periods WHERE property_id = ? AND year = ? AND month = ?",
        (property_id, year, month)
    ).fetchone()
    
    if period_row:
        period_id = period_row["id"]
        # Clear existing data for re-upload
        db.execute("DELETE FROM bank_transactions WHERE period_id = ?", (period_id,))
        db.execute("DELETE FROM yardi_transactions WHERE period_id = ?", (period_id,))
        db.execute("DELETE FROM matches WHERE period_id = ?", (period_id,))
    else:
        cursor = db.execute(
            "INSERT INTO reconciliation_periods (property_id, year, month) VALUES (?, ?, ?)",
            (property_id, year, month)
        )
        period_id = cursor.lastrowid
    
    db.commit()
    
    # Process uploaded files
    bank_file = request.files.get("bank_pdf")
    yardi_file = request.files.get("yardi_excel")
    
    bank_count = 0
    yardi_count = 0
    
    # Process bank PDF
    if bank_file and bank_file.filename and allowed_file(bank_file.filename):
        filename = secure_filename(bank_file.filename)
        upload_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
        bank_file.save(str(upload_path))
        
        try:
            from ..parsers import get_parser_for_pdf
            parser = get_parser_for_pdf(upload_path)
            
            if parser:
                transactions = parser.parse(upload_path)
                
                for txn in transactions:
                    db.execute("""
                        INSERT INTO bank_transactions 
                        (period_id, date, transaction_id, description, amount, transaction_type)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        period_id,
                        txn.date.strftime("%Y-%m-%d"),
                        txn.transaction_id,
                        txn.description,
                        txn.amount,
                        txn.transaction_type,
                    ))
                
                bank_count = len(transactions)
                db.commit()
                flash(f"Imported {bank_count} bank transactions from PDF.", "success")
            else:
                flash("Could not find a parser for this bank statement format.", "warning")
        except Exception as e:
            flash(f"Error parsing bank PDF: {str(e)}", "error")
        finally:
            # Clean up uploaded file
            if upload_path.exists():
                os.remove(upload_path)
    
    # Process Yardi Excel
    if yardi_file and yardi_file.filename and allowed_file(yardi_file.filename):
        filename = secure_filename(yardi_file.filename)
        upload_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
        yardi_file.save(str(upload_path))
        
        try:
            from ..parsers import extract_yardi_from_excel
            transactions, analysis = extract_yardi_from_excel(upload_path)
            
            # Log analysis results
            if analysis.get("suggested_name"):
                current_app.logger.info(
                    f"Yardi report analyzed: {analysis['original_name']} -> {analysis['suggested_name']} "
                    f"(confidence: {analysis['confidence']})"
                )
            
            for txn in transactions:
                db.execute("""
                    INSERT INTO yardi_transactions 
                    (period_id, date, transaction_id, description, amount, source_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    period_id,
                    txn["date"],
                    txn["transaction_id"],
                    txn["description"],
                    txn["amount"],
                    txn["source_type"],
                ))
            
            yardi_count = len(transactions)
            db.commit()
            flash(f"Imported {yardi_count} Yardi transactions from Excel.", "success")
        except Exception as e:
            flash(f"Error parsing Yardi Excel: {str(e)}", "error")
        finally:
            # Clean up uploaded file
            if upload_path.exists():
                os.remove(upload_path)
    
    if bank_count == 0 and yardi_count == 0:
        flash("No files were uploaded or processed.", "warning")
        return redirect(url_for("upload.index"))
    
    # Run auto-matching if we have data on both sides
    if bank_count > 0 and yardi_count > 0:
        try:
            from ..matching import run_auto_matching
            result = run_auto_matching(db, period_id)
            
            if result.total_matched > 0:
                flash(
                    f"Auto-matched {result.total_matched} transactions "
                    f"({result.unmatched_bank} bank + {result.unmatched_yardi} yardi unmatched).",
                    "success"
                )
            else:
                flash("No automatic matches found. Review unmatched transactions.", "info")
                
            if result.pass7_suggestions > 0:
                flash(
                    f"Found {result.pass7_suggestions} potential matches that need manual review.",
                    "info"
                )
        except Exception as e:
            current_app.logger.error(f"Auto-matching error: {e}")
            flash(f"Auto-matching error: {str(e)}", "error")
    elif bank_count > 0 or yardi_count > 0:
        flash("Upload both bank PDF and Yardi Excel to enable auto-matching.", "info")
    
    return redirect(url_for("dashboard.period_detail", period_id=period_id))
