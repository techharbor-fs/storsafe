"""
Upload Routes

Folder-based upload handling for bank statements and Yardi Excel files.
Validates that file contents match the expected month from folder name.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename

from ..database import get_db
from ..property_mapping import get_property_name

bp = Blueprint("upload", __name__, url_prefix="/upload")


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return (
        "." in filename 
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )


def parse_folder_month(folder_name: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse expected month and year from folder name.
    
    Patterns supported:
    - "12. Dec 2025" -> (12, 2025)
    - "12. Dec" -> (12, current_year)
    - "December 2025" -> (12, 2025)
    
    Returns:
        Tuple of (month, year) or (None, None) if not parseable
    """
    import re
    
    month_names = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
        'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
        'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    month = None
    year = datetime.now().year
    
    # First, try to extract year from anywhere in the folder name
    year_match = re.search(r'(\d{4})', folder_name)
    if year_match:
        potential_year = int(year_match.group(1))
        if 2020 <= potential_year <= 2030:
            year = potential_year
    
    # Pattern: "12. Dec" or "12. Dec 2025"
    match = re.search(r'(\d{1,2})\.\s*([a-zA-Z]+)', folder_name)
    if match:
        month_text = match.group(2).lower()
        if month_text in month_names:
            month = month_names[month_text]
    
    # Pattern: "December 2025" (if month not found yet)
    if not month:
        match = re.search(r'([a-zA-Z]+)\s*\d*', folder_name)
        if match:
            month_text = match.group(1).lower()
            if month_text in month_names:
                month = month_names[month_text]
    
    return month, year


def validate_bank_pdf_period(file_path: Path, expected_month: int, expected_year: int) -> Tuple[bool, str, List[str]]:
    """
    Validate that bank PDF contains transactions from the expected period.
    
    Returns:
        Tuple of (is_valid, property_name, error_messages)
    """
    errors = []
    property_name = None
    
    try:
        from ..parsers import get_parser_for_pdf
        parser = get_parser_for_pdf(file_path)
        
        if not parser:
            return False, None, ["Could not find a parser for this bank statement format."]
        
        transactions = parser.parse(file_path)
        
        if not transactions:
            return False, None, ["No transactions found in bank PDF."]
        
        # Extract property from parser if available
        property_name = getattr(parser, 'property_name', None)
        
        # Check transaction dates
        months_found = set()
        years_found = set()
        
        for txn in transactions:
            if txn.date:
                months_found.add(txn.date.month)
                years_found.add(txn.date.year)
        
        # Validate month
        if expected_month and expected_month not in months_found:
            month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']
            found_months = ', '.join(month_names[m] for m in sorted(months_found))
            errors.append(
                f"Bank PDF contains {found_months} data, but expected {month_names[expected_month]}."
            )
        
        # Validate year
        if expected_year and expected_year not in years_found:
            found_years = ', '.join(str(y) for y in sorted(years_found))
            errors.append(
                f"Bank PDF contains {found_years} data, but expected {expected_year}."
            )
        
        return len(errors) == 0, property_name, errors
        
    except Exception as e:
        return False, None, [f"Error parsing bank PDF: {str(e)}"]


def validate_yardi_excel_period(file_path: Path, expected_month: int, expected_year: int) -> Tuple[bool, str, List[str]]:
    """
    Validate that Yardi Excel contains data from the expected period.
    
    Returns:
        Tuple of (is_valid, property_name, error_messages)
    """
    errors = []
    property_name = None
    
    try:
        from ..parsers import extract_yardi_from_excel, analyze_yardi_report
        
        # Analyze the report first
        analysis = analyze_yardi_report(file_path)
        property_name = analysis.get('property')
        detected_month = analysis.get('month')
        detected_year = analysis.get('year')
        
        # Validate month
        if expected_month and detected_month and detected_month != expected_month:
            month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']
            errors.append(
                f"Yardi Excel contains {month_names[detected_month]} data, but expected {month_names[expected_month]}."
            )
        
        # Validate year
        if expected_year and detected_year and detected_year != expected_year:
            errors.append(
                f"Yardi Excel contains {detected_year} data, but expected {expected_year}."
            )
        
        return len(errors) == 0, property_name, errors
        
    except Exception as e:
        return False, None, [f"Error analyzing Yardi Excel: {str(e)}"]


@bp.route("/", methods=["GET"])
def index():
    """Upload page with folder selector."""
    db = get_db()
    
    # Get existing properties for dropdown
    properties = db.execute(
        "SELECT id, name FROM properties ORDER BY name"
    ).fetchall()
    
    return render_template("upload.html", properties=properties)


@bp.route("/folder", methods=["POST"])
def upload_folder():
    """Handle folder-based upload with validation."""
    db = get_db()
    
    # Get form data
    folder_name = request.form.get("folder_name", "").strip()
    expected_month = request.form.get("expected_month", type=int)
    expected_year = request.form.get("expected_year", type=int)
    property_override = request.form.get("property_name", "").strip()
    
    # Get uploaded files
    bank_file = request.files.get("bank_pdf")
    yardi_file = request.files.get("yardi_excel")
    
    if not bank_file or not bank_file.filename:
        flash("Bank PDF file is required.", "error")
        return redirect(url_for("upload.index"))
    
    if not yardi_file or not yardi_file.filename:
        flash("Yardi Excel file is required.", "error")
        return redirect(url_for("upload.index"))
    
    # Parse expected period from folder name if not provided
    if not expected_month or not expected_year:
        expected_month, expected_year = parse_folder_month(folder_name)
    
    if not expected_month:
        flash(f"Could not determine expected month from folder name '{folder_name}'. Please select manually.", "error")
        return redirect(url_for("upload.index"))
    
    # Save files temporarily for validation
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    
    bank_filename = secure_filename(bank_file.filename)
    yardi_filename = secure_filename(yardi_file.filename)
    
    bank_path = upload_folder / bank_filename
    yardi_path = upload_folder / yardi_filename
    
    bank_file.save(str(bank_path))
    yardi_file.save(str(yardi_path))
    
    validation_errors = []
    detected_property = None
    
    try:
        # Validate bank PDF
        bank_valid, bank_property, bank_errors = validate_bank_pdf_period(
            bank_path, expected_month, expected_year
        )
        validation_errors.extend(bank_errors)
        if bank_property:
            detected_property = bank_property
        
        # Validate Yardi Excel
        yardi_valid, yardi_property, yardi_errors = validate_yardi_excel_period(
            yardi_path, expected_month, expected_year
        )
        validation_errors.extend(yardi_errors)
        if yardi_property and not detected_property:
            detected_property = yardi_property
        
        # If validation failed, show errors
        if validation_errors:
            for error in validation_errors:
                flash(error, "error")
            
            # Clean up
            if bank_path.exists():
                os.remove(bank_path)
            if yardi_path.exists():
                os.remove(yardi_path)
            
            return redirect(url_for("upload.index"))
        
        # Determine property name (apply mapping to convert codes to display names)
        raw_property = property_override or detected_property or "Unknown Property"
        property_name = get_property_name(raw_property)
        
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
            (property_id, expected_year, expected_month)
        ).fetchone()
        
        if period_row:
            period_id = period_row["id"]
            # Clear existing data for re-upload
            db.execute("DELETE FROM bank_transactions WHERE period_id = ?", (period_id,))
            db.execute("DELETE FROM yardi_transactions WHERE period_id = ?", (period_id,))
            db.execute("DELETE FROM matches WHERE period_id = ?", (period_id,))
            flash(f"Replacing existing data for {property_name} - {expected_month}/{expected_year}.", "info")
        else:
            cursor = db.execute(
                "INSERT INTO reconciliation_periods (property_id, year, month) VALUES (?, ?, ?)",
                (property_id, expected_year, expected_month)
            )
            period_id = cursor.lastrowid
        
        db.commit()
        
        # Process bank PDF
        bank_count = 0
        try:
            from ..parsers import get_parser_for_pdf
            parser = get_parser_for_pdf(bank_path)
            
            if parser:
                transactions = parser.parse(bank_path)
                
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
        except Exception as e:
            flash(f"Error processing bank PDF: {str(e)}", "error")
        
        # Process Yardi Excel
        yardi_count = 0
        try:
            from ..parsers import extract_yardi_from_excel
            transactions, analysis = extract_yardi_from_excel(yardi_path)
            
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
            flash(f"Error processing Yardi Excel: {str(e)}", "error")
        
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
        
        return redirect(url_for("dashboard.period_detail", period_id=period_id))
        
    finally:
        # Clean up uploaded files
        if bank_path.exists():
            os.remove(bank_path)
        if yardi_path.exists():
            os.remove(yardi_path)
