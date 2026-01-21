"""
Bank Reconciliation Matching Engine

Implements the 7-pass matching algorithm to reconcile bank transactions
with Yardi transactions.

Matching Passes:
- PASS 1: Property + Transaction ID + Amount (strict 1:1)
- PASS 2: Property + Date + Amount (strict 1:1)
- PASS 3: Property + Amount + Date within ±3 days (strict 1:1)
- PASS 4: Property + Amount + Date within ±7 days (strict 1:1)
- PASS 5: Same-side reversals (Bank↔Bank or Yardi↔Yardi, opposite signs, same date)
- PASS 6: Property + Amount (exact) - only if counts match perfectly
- PASS 7: Property + Amount (exact) but incomplete pairing - suggested matches only
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Set, Tuple
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class MatchingResult:
    """Results from the matching process."""
    
    # Counts
    bank_total: int = 0
    yardi_total: int = 0
    
    # Bank↔Yardi matches by pass
    pass1_matches: int = 0
    pass2_matches: int = 0
    pass3_matches: int = 0
    pass4_matches: int = 0
    pass6_matches: int = 0
    
    # Same-side matches (PASS 5)
    pass5_bank_matches: int = 0  # Bank↔Bank reversal pairs
    pass5_yardi_matches: int = 0  # Yardi↔Yardi reversal pairs
    
    # Suggested matches (PASS 7)
    pass7_suggestions: int = 0
    
    # Unmatched
    unmatched_bank: int = 0
    unmatched_yardi: int = 0
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    @property
    def total_matched(self) -> int:
        """Total number of confirmed matches."""
        return (
            self.pass1_matches + self.pass2_matches + 
            self.pass3_matches + self.pass4_matches +
            self.pass5_bank_matches + self.pass5_yardi_matches +
            self.pass6_matches
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/display."""
        return {
            "bank_total": self.bank_total,
            "yardi_total": self.yardi_total,
            "matches": {
                "pass1": self.pass1_matches,
                "pass2": self.pass2_matches,
                "pass3": self.pass3_matches,
                "pass4": self.pass4_matches,
                "pass5_bank": self.pass5_bank_matches,
                "pass5_yardi": self.pass5_yardi_matches,
                "pass6": self.pass6_matches,
                "total": self.total_matched,
            },
            "suggestions": self.pass7_suggestions,
            "unmatched_bank": self.unmatched_bank,
            "unmatched_yardi": self.unmatched_yardi,
            "errors": self.errors,
        }


def run_auto_matching(db: sqlite3.Connection, period_id: int) -> MatchingResult:
    """
    Run the 7-pass matching algorithm for a reconciliation period.
    
    Args:
        db: SQLite database connection
        period_id: ID of the reconciliation period to match
        
    Returns:
        MatchingResult with counts and statistics
    """
    result = MatchingResult()
    
    # Clear any existing matches for this period
    db.execute("DELETE FROM matches WHERE period_id = ?", (period_id,))
    db.commit()
    
    # Load bank transactions
    bank_rows = db.execute("""
        SELECT id, date, transaction_id, description, amount, transaction_type
        FROM bank_transactions
        WHERE period_id = ?
        ORDER BY date, id
    """, (period_id,)).fetchall()
    
    # Load yardi transactions
    yardi_rows = db.execute("""
        SELECT id, date, transaction_id, description, amount, source_type
        FROM yardi_transactions
        WHERE period_id = ?
        ORDER BY date, id
    """, (period_id,)).fetchall()
    
    result.bank_total = len(bank_rows)
    result.yardi_total = len(yardi_rows)
    
    if not bank_rows or not yardi_rows:
        logger.info(f"Period {period_id}: One or both sides empty. Bank={len(bank_rows)}, Yardi={len(yardi_rows)}")
        result.unmatched_bank = len(bank_rows)
        result.unmatched_yardi = len(yardi_rows)
        return result
    
    # Normalize data into dictionaries
    bank_norm = _normalize_transactions(bank_rows, "bank")
    yardi_norm = _normalize_transactions(yardi_rows, "yardi")
    
    # Track what's been matched
    matched_bank: Set[int] = set()  # bank db IDs
    matched_yardi: Set[int] = set()  # yardi db IDs
    
    # Results storage: list of (pass_name, match_type, bank_ids, yardi_ids)
    all_matches: List[Tuple[str, str, List[int], List[int]]] = []
    
    # Build indices for efficient lookup
    indices = _build_indices(bank_norm, yardi_norm)
    
    # =========================================================================
    # PASS 1: Property + Transaction ID + Amount (strict 1:1)
    # =========================================================================
    pass1_count = _run_pass1(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches
    )
    result.pass1_matches = pass1_count
    logger.debug(f"PASS 1: {pass1_count} matches")
    
    # =========================================================================
    # PASS 2: Property + Date + Amount (strict 1:1)
    # =========================================================================
    pass2_count = _run_pass2(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches
    )
    result.pass2_matches = pass2_count
    logger.debug(f"PASS 2: {pass2_count} matches")
    
    # =========================================================================
    # PASS 3: Property + Amount + Date within ±3 days (strict 1:1)
    # =========================================================================
    pass3_count = _run_pass3(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches,
        day_tolerance=3
    )
    result.pass3_matches = pass3_count
    logger.debug(f"PASS 3: {pass3_count} matches")
    
    # =========================================================================
    # PASS 4: Property + Amount + Date within ±7 days (strict 1:1)
    # =========================================================================
    pass4_count = _run_pass4(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches,
        day_tolerance=7
    )
    result.pass4_matches = pass4_count
    logger.debug(f"PASS 4: {pass4_count} matches")
    
    # =========================================================================
    # PASS 5: Same-side reversals (opposite signs, same date, same absolute amount)
    # =========================================================================
    pass5_bank, pass5_yardi = _run_pass5(
        bank_norm, yardi_norm,
        matched_bank, matched_yardi, all_matches
    )
    result.pass5_bank_matches = pass5_bank
    result.pass5_yardi_matches = pass5_yardi
    logger.debug(f"PASS 5: {pass5_bank} bank reversals, {pass5_yardi} yardi reversals")
    
    # =========================================================================
    # PASS 6: Property + Amount (exact) - only if counts match perfectly
    # =========================================================================
    pass6_count = _run_pass6(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches
    )
    result.pass6_matches = pass6_count
    logger.debug(f"PASS 6: {pass6_count} matches")
    
    # =========================================================================
    # PASS 7: Property + Amount (exact) but incomplete - suggested matches
    # These are NOT stored as confirmed matches, just flagged for review
    # =========================================================================
    pass7_count = _run_pass7(
        bank_norm, yardi_norm, indices,
        matched_bank, matched_yardi, all_matches
    )
    result.pass7_suggestions = pass7_count
    logger.debug(f"PASS 7: {pass7_count} suggestions")
    
    # =========================================================================
    # Save all matches to database
    # =========================================================================
    _save_matches_to_db(db, period_id, all_matches)
    db.commit()
    
    # Calculate unmatched counts
    result.unmatched_bank = len(bank_norm) - len(matched_bank)
    result.unmatched_yardi = len(yardi_norm) - len(matched_yardi)
    
    # Log detailed results
    current_app_logger = None
    try:
        from flask import current_app
        current_app_logger = current_app.logger
    except RuntimeError:
        pass  # Not in Flask context
    
    log_fn = current_app_logger.info if current_app_logger else logger.info
    log_fn(
        f"Period {period_id} matching complete: "
        f"PASS1={result.pass1_matches}, PASS2={result.pass2_matches}, "
        f"PASS3={result.pass3_matches}, PASS4={result.pass4_matches}, "
        f"PASS5(bank)={result.pass5_bank_matches}, PASS5(yardi)={result.pass5_yardi_matches}, "
        f"PASS6={result.pass6_matches}, PASS7={result.pass7_suggestions}"
    )
    log_fn(
        f"Period {period_id} totals: "
        f"{result.total_matched} matched, "
        f"{result.unmatched_bank} unmatched bank, "
        f"{result.unmatched_yardi} unmatched yardi"
    )
    
    return result


def _normalize_transactions(rows: List[sqlite3.Row], source: str) -> List[Dict]:
    """
    Normalize transaction rows into dictionaries for matching.
    
    Args:
        rows: List of database rows
        source: 'bank' or 'yardi'
        
    Returns:
        List of normalized transaction dictionaries
    """
    normalized = []
    for row in rows:
        # Parse date (stored as YYYY-MM-DD string in SQLite)
        date_val = row["date"]
        if isinstance(date_val, str):
            try:
                date_obj = datetime.strptime(date_val, "%Y-%m-%d")
            except ValueError:
                date_obj = None
        elif isinstance(date_val, (datetime, date)):
            date_obj = date_val if isinstance(date_val, datetime) else datetime.combine(date_val, datetime.min.time())
        else:
            date_obj = None
        
        normalized.append({
            "id": row["id"],  # Database ID
            "date": date_obj,
            "txid": (row["transaction_id"] or "").strip(),
            "desc": (row["description"] or "").strip(),
            "amt": row["amount"],
            "source": source,
        })
    
    return normalized


def _cents(amount: Optional[float]) -> Optional[int]:
    """Convert amount to cents to avoid float comparison issues."""
    if amount is None:
        return None
    return int(round(amount * 100))


def _normalize_date(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to midnight for comparison."""
    if dt is None:
        return None
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _build_indices(bank_norm: List[Dict], yardi_norm: List[Dict]) -> Dict:
    """
    Build lookup indices for efficient matching.
    
    Returns:
        Dictionary of various indices
    """
    indices = {
        # Yardi by transaction ID: {txid: [yardi_indices]}
        "yardi_by_txid": {},
        # Yardi by (cents, date): {(cents, date): [yardi_indices]}
        "yardi_by_amt_date": {},
        # Yardi by cents: {cents: [yardi_indices]}
        "yardi_by_amt": {},
        # Bank by cents: {cents: [bank_indices]}
        "bank_by_amt": {},
    }
    
    for idx, y in enumerate(yardi_norm):
        # By transaction ID
        if y["txid"]:
            indices["yardi_by_txid"].setdefault(y["txid"], []).append(idx)
        
        # By amount + date
        if y["amt"] is not None and y["date"] is not None:
            key = (_cents(y["amt"]), _normalize_date(y["date"]))
            indices["yardi_by_amt_date"].setdefault(key, []).append(idx)
        
        # By amount only
        if y["amt"] is not None:
            indices["yardi_by_amt"].setdefault(_cents(y["amt"]), []).append(idx)
    
    for idx, b in enumerate(bank_norm):
        if b["amt"] is not None:
            indices["bank_by_amt"].setdefault(_cents(b["amt"]), []).append(idx)
    
    return indices


def _run_pass1(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple]
) -> int:
    """
    PASS 1: Match by Property + Transaction ID + Amount (strict 1:1)
    
    Only matches if there's exactly one unmatched Yardi transaction
    with the same txid and amount.
    """
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if not b["txid"] or b["amt"] is None:
            continue
        
        # Find Yardi transactions with same txid
        candidates = indices["yardi_by_txid"].get(b["txid"], [])
        
        # Filter to unmatched with matching amount
        filtered = []
        for y_idx in candidates:
            y = yardi_norm[y_idx]
            if y["id"] in matched_yardi:
                continue
            if y["amt"] is None:
                continue
            if _cents(y["amt"]) != _cents(b["amt"]):
                continue
            filtered.append(y_idx)
        
        # Only match if exactly one candidate (strict 1:1)
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 1", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass2(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple]
) -> int:
    """
    PASS 2: Match by Property + Date + Amount (strict 1:1)
    """
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        # Find Yardi transactions with same amount and date
        key = (_cents(b["amt"]), _normalize_date(b["date"]))
        candidates = indices["yardi_by_amt_date"].get(key, [])
        
        # Filter to unmatched
        filtered = [y_idx for y_idx in candidates if yardi_norm[y_idx]["id"] not in matched_yardi]
        
        # Only match if exactly one candidate
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 2", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass3(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple],
    day_tolerance: int = 3
) -> int:
    """
    PASS 3: Match by Property + Amount + Date within ±N days (strict 1:1)
    """
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        # Find Yardi transactions with same amount
        candidates = indices["yardi_by_amt"].get(_cents(b["amt"]), [])
        
        # Filter to unmatched within date tolerance
        filtered = []
        for y_idx in candidates:
            y = yardi_norm[y_idx]
            if y["id"] in matched_yardi:
                continue
            if y["date"] is None:
                continue
            day_diff = abs((b["date"] - y["date"]).days)
            if day_diff <= day_tolerance:
                filtered.append(y_idx)
        
        # Only match if exactly one candidate
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 3", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass4(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple],
    day_tolerance: int = 7
) -> int:
    """
    PASS 4: Match by Property + Amount + Date within ±N days (strict 1:1)
    Same as PASS 3 but with wider date tolerance.
    """
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        # Find Yardi transactions with same amount
        candidates = indices["yardi_by_amt"].get(_cents(b["amt"]), [])
        
        # Filter to unmatched within date tolerance
        filtered = []
        for y_idx in candidates:
            y = yardi_norm[y_idx]
            if y["id"] in matched_yardi:
                continue
            if y["date"] is None:
                continue
            day_diff = abs((b["date"] - y["date"]).days)
            if day_diff <= day_tolerance:
                filtered.append(y_idx)
        
        # Only match if exactly one candidate
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 4", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass5(
    bank_norm: List[Dict], yardi_norm: List[Dict],
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple]
) -> Tuple[int, int]:
    """
    PASS 5: Same-side reversals (Bank↔Bank or Yardi↔Yardi)
    
    Matches transactions with opposite signs, same absolute amount, same date.
    This catches payment reversals and corrections.
    
    Returns:
        Tuple of (bank_reversal_count, yardi_reversal_count)
    """
    bank_count = 0
    yardi_count = 0
    
    # -------------------------------------------------------------------------
    # Bank↔Bank reversals
    # -------------------------------------------------------------------------
    # Build index: (date, abs_cents) -> [bank_indices]
    bank_by_date_abs_amt: Dict[Tuple, List[int]] = {}
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        key = (_normalize_date(b["date"]), abs(_cents(b["amt"])))
        bank_by_date_abs_amt.setdefault(key, []).append(b_idx)
    
    # Find pairs with opposite signs
    matched_bank_pass5: Set[int] = set()
    for key, bank_indices in bank_by_date_abs_amt.items():
        if len(bank_indices) < 2:
            continue
        
        # Separate by sign
        positive = [idx for idx in bank_indices if bank_norm[idx]["amt"] > 0 and bank_norm[idx]["id"] not in matched_bank_pass5]
        negative = [idx for idx in bank_indices if bank_norm[idx]["amt"] < 0 and bank_norm[idx]["id"] not in matched_bank_pass5]
        
        # Match 1:1
        for pos_idx, neg_idx in zip(positive, negative):
            pos_id = bank_norm[pos_idx]["id"]
            neg_id = bank_norm[neg_idx]["id"]
            
            matched_bank.add(pos_id)
            matched_bank.add(neg_id)
            matched_bank_pass5.add(pos_id)
            matched_bank_pass5.add(neg_id)
            
            all_matches.append(("PASS 5", "bank_bank", [neg_id, pos_id], []))
            bank_count += 1
    
    # -------------------------------------------------------------------------
    # Yardi↔Yardi reversals
    # -------------------------------------------------------------------------
    yardi_by_date_abs_amt: Dict[Tuple, List[int]] = {}
    for y_idx, y in enumerate(yardi_norm):
        if y["id"] in matched_yardi:
            continue
        if y["amt"] is None or y["date"] is None:
            continue
        key = (_normalize_date(y["date"]), abs(_cents(y["amt"])))
        yardi_by_date_abs_amt.setdefault(key, []).append(y_idx)
    
    matched_yardi_pass5: Set[int] = set()
    for key, yardi_indices in yardi_by_date_abs_amt.items():
        if len(yardi_indices) < 2:
            continue
        
        positive = [idx for idx in yardi_indices if yardi_norm[idx]["amt"] > 0 and yardi_norm[idx]["id"] not in matched_yardi_pass5]
        negative = [idx for idx in yardi_indices if yardi_norm[idx]["amt"] < 0 and yardi_norm[idx]["id"] not in matched_yardi_pass5]
        
        for pos_idx, neg_idx in zip(positive, negative):
            pos_id = yardi_norm[pos_idx]["id"]
            neg_id = yardi_norm[neg_idx]["id"]
            
            matched_yardi.add(pos_id)
            matched_yardi.add(neg_id)
            matched_yardi_pass5.add(pos_id)
            matched_yardi_pass5.add(neg_id)
            
            all_matches.append(("PASS 5", "yardi_yardi", [], [neg_id, pos_id]))
            yardi_count += 1
    
    return bank_count, yardi_count


def _run_pass6(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple]
) -> int:
    """
    PASS 6: Match by Property + Amount (exact) - only if counts match perfectly
    
    Only matches if the number of unmatched bank transactions equals the number
    of unmatched Yardi transactions with the same amount.
    """
    count = 0
    
    # Build buckets of unmatched by amount
    bank_by_amt: Dict[int, List[int]] = {}
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None:
            continue
        cents = _cents(b["amt"])
        bank_by_amt.setdefault(cents, []).append(b_idx)
    
    yardi_by_amt: Dict[int, List[int]] = {}
    for y_idx, y in enumerate(yardi_norm):
        if y["id"] in matched_yardi:
            continue
        if y["amt"] is None:
            continue
        cents = _cents(y["amt"])
        yardi_by_amt.setdefault(cents, []).append(y_idx)
    
    # Find amounts that exist on both sides
    common_amounts = set(bank_by_amt.keys()) & set(yardi_by_amt.keys())
    
    for amt in common_amounts:
        bank_indices = bank_by_amt[amt]
        yardi_indices = yardi_by_amt[amt]
        
        # Only match if counts are equal
        if len(bank_indices) != len(yardi_indices):
            continue
        
        # Pair them up 1:1
        for b_idx, y_idx in zip(bank_indices, yardi_indices):
            b = bank_norm[b_idx]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 6", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass7(
    bank_norm: List[Dict], yardi_norm: List[Dict], indices: Dict,
    matched_bank: Set[int], matched_yardi: Set[int],
    all_matches: List[Tuple]
) -> int:
    """
    PASS 7: Property + Amount (exact) but incomplete pairing - suggested matches
    
    These are NOT confirmed matches. They're stored as suggestions for manual review.
    A PASS 7 "match" means the amounts match but there's an unequal count,
    so the user needs to decide which ones actually pair up.
    """
    count = 0
    
    # Build buckets of still-unmatched by amount
    bank_by_amt: Dict[int, List[int]] = {}
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None:
            continue
        cents = _cents(b["amt"])
        bank_by_amt.setdefault(cents, []).append(b_idx)
    
    yardi_by_amt: Dict[int, List[int]] = {}
    for y_idx, y in enumerate(yardi_norm):
        if y["id"] in matched_yardi:
            continue
        if y["amt"] is None:
            continue
        cents = _cents(y["amt"])
        yardi_by_amt.setdefault(cents, []).append(y_idx)
    
    # Find amounts where there ARE matches but counts differ
    common_amounts = set(bank_by_amt.keys()) & set(yardi_by_amt.keys())
    
    for amt in common_amounts:
        bank_indices = bank_by_amt[amt]
        yardi_indices = yardi_by_amt[amt]
        
        # Only flag if counts differ (PASS 6 would have caught equal counts)
        if len(bank_indices) == len(yardi_indices):
            continue
        
        # Store as a suggestion - don't mark as matched
        # Each bank transaction gets a suggestion pointing to potential yardi matches
        bank_ids = [bank_norm[i]["id"] for i in bank_indices]
        yardi_ids = [yardi_norm[i]["id"] for i in yardi_indices]
        
        all_matches.append(("PASS 7", "suggestion", bank_ids, yardi_ids))
        count += 1
    
    return count


def _save_matches_to_db(
    db: sqlite3.Connection, 
    period_id: int, 
    all_matches: List[Tuple[str, str, List[int], List[int]]]
):
    """
    Save all matches to the database.
    
    Args:
        db: Database connection
        period_id: Reconciliation period ID
        all_matches: List of (pass_name, match_type, bank_ids, yardi_ids)
    """
    for pass_name, match_type, bank_ids, yardi_ids in all_matches:
        # Insert the match record
        cursor = db.execute("""
            INSERT INTO matches (period_id, match_pass, match_type)
            VALUES (?, ?, ?)
        """, (period_id, pass_name, match_type))
        match_id = cursor.lastrowid
        
        # Insert bank transaction links
        for bank_id in bank_ids:
            db.execute("""
                INSERT INTO match_bank_transactions (match_id, bank_transaction_id)
                VALUES (?, ?)
            """, (match_id, bank_id))
        
        # Insert yardi transaction links
        for yardi_id in yardi_ids:
            db.execute("""
                INSERT INTO match_yardi_transactions (match_id, yardi_transaction_id)
                VALUES (?, ?)
            """, (match_id, yardi_id))
