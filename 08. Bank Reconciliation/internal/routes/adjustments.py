"""
Adjustment Entry Routes

Handles CRUD operations for adjustment entries and smart suggestions.
"""

from flask import Blueprint, request, jsonify, flash, redirect, url_for

from ..database import get_db

bp = Blueprint("adjustments", __name__, url_prefix="/adjustments")


# Category display names
CATEGORY_LABELS = {
    'nsf_fee': 'NSF Fee',
    'overdraft_fee': 'Overdraft Fee',
    'bank_charge': 'Bank Charge',
    'interest_income': 'Interest Income',
    'wire_fee': 'Wire Fee',
    'other': 'Other',
}


def get_suggested_category(description: str, property_id: int = None) -> tuple[str | None, float]:
    """
    Get suggested category for a transaction based on patterns.
    
    Returns:
        Tuple of (category, confidence) or (None, 0) if no match
    """
    db = get_db()
    
    if not description:
        return None, 0
    
    desc_lower = description.lower()
    
    # Check patterns (property-specific first, then global)
    patterns = db.execute("""
        SELECT pattern_value, category, confidence
        FROM adjustment_patterns
        WHERE pattern_type = 'keyword'
        AND (property_id = ? OR property_id IS NULL)
        ORDER BY property_id DESC NULLS LAST, confidence DESC
    """, (property_id,)).fetchall()
    
    for pattern in patterns:
        if pattern["pattern_value"].lower() in desc_lower:
            return pattern["category"], pattern["confidence"]
    
    return None, 0


def get_adjustments_for_period(period_id: int) -> list[dict]:
    """Get all adjustment entries for a period."""
    db = get_db()
    
    adjustments = db.execute("""
        SELECT 
            ae.*,
            bt.description as bank_desc,
            bt.amount as bank_amount
        FROM adjustment_entries ae
        LEFT JOIN bank_transactions bt ON ae.source_bank_txn_id = bt.id
        WHERE ae.period_id = ?
        ORDER BY ae.confirmed DESC, ae.suggested DESC, ae.date ASC
    """, (period_id,)).fetchall()
    
    return [dict(row) for row in adjustments]


def get_suggested_adjustments(period_id: int) -> list[dict]:
    """
    Analyze unmatched bank transactions and suggest potential adjustments.
    
    Returns list of suggestions with:
    - bank_txn: the bank transaction
    - category: suggested category
    - confidence: confidence score
    - reason: why it was suggested
    """
    db = get_db()
    
    # Get period's property_id
    period = db.execute(
        "SELECT property_id FROM reconciliation_periods WHERE id = ?",
        (period_id,)
    ).fetchone()
    
    if not period:
        return []
    
    property_id = period["property_id"]
    
    # Get unmatched bank transactions
    unmatched = db.execute("""
        SELECT bt.*
        FROM bank_transactions bt
        WHERE bt.period_id = ?
        AND NOT EXISTS (
            SELECT 1 FROM match_bank_transactions mbt
            WHERE mbt.bank_transaction_id = bt.id
        )
        AND NOT EXISTS (
            SELECT 1 FROM adjustment_entries ae
            WHERE ae.source_bank_txn_id = bt.id
        )
        ORDER BY bt.date ASC
    """, (period_id,)).fetchall()
    
    suggestions = []
    
    for txn in unmatched:
        category, confidence = get_suggested_category(txn["description"], property_id)
        
        if category and confidence >= 0.7:
            suggestions.append({
                "bank_txn": dict(txn),
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "confidence": confidence,
                "reason": f"Description matches '{category}' pattern",
            })
    
    return suggestions


@bp.route("/period/<int:period_id>", methods=["GET"])
def list_adjustments(period_id: int):
    """Get all adjustments for a period (API endpoint)."""
    adjustments = get_adjustments_for_period(period_id)
    suggestions = get_suggested_adjustments(period_id)
    
    return jsonify({
        "adjustments": adjustments,
        "suggestions": suggestions,
        "category_labels": CATEGORY_LABELS,
    })


@bp.route("/period/<int:period_id>/create", methods=["POST"])
def create_adjustment(period_id: int):
    """Create a new adjustment entry from a bank transaction."""
    db = get_db()
    
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    bank_txn_id = data.get("bank_txn_id")
    category = data.get("category", "other")
    notes = data.get("notes", "")
    
    # Verify bank transaction exists and belongs to this period
    bank_txn = db.execute("""
        SELECT * FROM bank_transactions
        WHERE id = ? AND period_id = ?
    """, (bank_txn_id, period_id)).fetchone()
    
    if not bank_txn:
        return jsonify({"success": False, "error": "Bank transaction not found"}), 404
    
    # Check if already an adjustment
    existing = db.execute("""
        SELECT id FROM adjustment_entries
        WHERE source_bank_txn_id = ?
    """, (bank_txn_id,)).fetchone()
    
    if existing:
        return jsonify({"success": False, "error": "Transaction is already an adjustment"}), 400
    
    # Create adjustment entry
    cursor = db.execute("""
        INSERT INTO adjustment_entries 
        (period_id, source_type, source_bank_txn_id, date, description, amount, category, confirmed, notes)
        VALUES (?, 'bank', ?, ?, ?, ?, ?, TRUE, ?)
    """, (
        period_id,
        bank_txn_id,
        bank_txn["date"],
        bank_txn["description"],
        bank_txn["amount"],
        category,
        notes,
    ))
    
    adjustment_id = cursor.lastrowid
    db.commit()
    
    # Update pattern confidence if this was a suggested category
    db.execute("""
        UPDATE adjustment_patterns
        SET times_used = times_used + 1, confidence = MIN(confidence + 0.05, 1.0)
        WHERE pattern_type = 'keyword' 
        AND ? LIKE '%' || pattern_value || '%'
        AND category = ?
    """, (bank_txn["description"].lower() if bank_txn["description"] else "", category))
    db.commit()
    
    return jsonify({
        "success": True,
        "adjustment_id": adjustment_id,
        "message": "Adjustment created successfully",
    })


@bp.route("/period/<int:period_id>/create-differential", methods=["POST"])
def create_differential_adjustment(period_id: int):
    """Create an adjustment entry for the difference in an unequal match."""
    db = get_db()
    
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        is_form = False
    else:
        data = request.form.to_dict()
        is_form = True
    
    if not data:
        if is_form:
            flash("No data provided.", "error")
            return redirect(url_for("dashboard.period_detail", period_id=period_id))
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    match_id = data.get("match_id")
    bank_total = float(data.get("bank_total", 0))
    yardi_total = float(data.get("yardi_total", 0))
    notes = data.get("notes", "")
    
    difference = round(bank_total - yardi_total, 2)
    
    if abs(difference) < 0.01:
        if is_form:
            flash("No difference to adjust.", "error")
            return redirect(url_for("dashboard.period_detail", period_id=period_id))
        return jsonify({"success": False, "error": "No difference to adjust"}), 400
    
    # Verify match exists
    match = db.execute("""
        SELECT * FROM matches WHERE id = ? AND period_id = ?
    """, (match_id, period_id)).fetchone()
    
    if not match:
        if is_form:
            flash("Match not found.", "error")
            return redirect(url_for("dashboard.period_detail", period_id=period_id))
        return jsonify({"success": False, "error": "Match not found"}), 404
    
    # Check if adjustment already exists
    existing = db.execute(
        "SELECT id FROM adjustment_entries WHERE source_match_id = ?",
        (match_id,)
    ).fetchone()
    
    if existing:
        if is_form:
            flash("Adjustment already recorded for this match.", "info")
            return redirect(url_for("dashboard.period_detail", period_id=period_id))
        return jsonify({"success": False, "error": "Adjustment already exists"}), 400
    
    # Create adjustment entry for the difference
    cursor = db.execute("""
        INSERT INTO adjustment_entries 
        (period_id, source_type, source_match_id, date, description, amount, category, confirmed, notes)
        VALUES (?, 'differential', ?, DATE('now'), ?, ?, 'other', TRUE, ?)
    """, (
        period_id,
        match_id,
        f"Adjustment for match differential (Bank: ${bank_total:,.2f}, Yardi: ${yardi_total:,.2f})",
        difference,
        notes,
    ))
    
    adjustment_id = cursor.lastrowid
    db.commit()
    
    if is_form:
        flash(f"Adjustment of ${abs(difference):,.2f} recorded.", "success")
        return redirect(url_for("dashboard.period_detail", period_id=period_id))
    
    return jsonify({
        "success": True,
        "adjustment_id": adjustment_id,
        "difference": difference,
        "message": f"Differential adjustment of ${difference:,.2f} created",
    })


@bp.route("/<int:adjustment_id>/update", methods=["POST"])
def update_adjustment(adjustment_id: int):
    """Update an adjustment entry."""
    db = get_db()
    
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    # Verify adjustment exists
    adjustment = db.execute(
        "SELECT * FROM adjustment_entries WHERE id = ?", (adjustment_id,)
    ).fetchone()
    
    if not adjustment:
        return jsonify({"success": False, "error": "Adjustment not found"}), 404
    
    # Update fields
    category = data.get("category", adjustment["category"])
    notes = data.get("notes", adjustment["notes"])
    confirmed = data.get("confirmed", adjustment["confirmed"])
    
    db.execute("""
        UPDATE adjustment_entries
        SET category = ?, notes = ?, confirmed = ?
        WHERE id = ?
    """, (category, notes, confirmed, adjustment_id))
    db.commit()
    
    return jsonify({
        "success": True,
        "message": "Adjustment updated",
    })


@bp.route("/<int:adjustment_id>/delete", methods=["POST"])
def delete_adjustment(adjustment_id: int):
    """Delete an adjustment entry."""
    db = get_db()
    
    # Get adjustment to find period_id for redirect
    adjustment = db.execute(
        "SELECT period_id FROM adjustment_entries WHERE id = ?", (adjustment_id,)
    ).fetchone()
    
    if not adjustment:
        return jsonify({"success": False, "error": "Adjustment not found"}), 404
    
    db.execute("DELETE FROM adjustment_entries WHERE id = ?", (adjustment_id,))
    db.commit()
    
    return jsonify({
        "success": True,
        "message": "Adjustment deleted",
    })


@bp.route("/period/<int:period_id>/suggest-all", methods=["POST"])
def auto_suggest_adjustments(period_id: int):
    """Auto-create suggested adjustments for high-confidence matches."""
    db = get_db()
    
    suggestions = get_suggested_adjustments(period_id)
    created = 0
    
    for suggestion in suggestions:
        if suggestion["confidence"] >= 0.9:  # Only auto-create high confidence
            bank_txn = suggestion["bank_txn"]
            
            # Check if already exists
            existing = db.execute("""
                SELECT id FROM adjustment_entries
                WHERE source_bank_txn_id = ?
            """, (bank_txn["id"],)).fetchone()
            
            if not existing:
                db.execute("""
                    INSERT INTO adjustment_entries 
                    (period_id, source_type, source_bank_txn_id, date, description, amount, category, suggested, confirmed, notes)
                    VALUES (?, 'bank', ?, ?, ?, ?, ?, TRUE, FALSE, ?)
                """, (
                    period_id,
                    bank_txn["id"],
                    bank_txn["date"],
                    bank_txn["description"],
                    bank_txn["amount"],
                    suggestion["category"],
                    f"Auto-suggested: {suggestion['reason']}",
                ))
                created += 1
    
    db.commit()
    
    return jsonify({
        "success": True,
        "created": created,
        "message": f"Created {created} suggested adjustments",
    })
