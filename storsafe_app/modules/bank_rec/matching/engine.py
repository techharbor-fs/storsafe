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


def run_auto_matching(period_id: int) -> MatchingResult:
    """
    Run the 7-pass matching algorithm for a reconciliation period.
    
    This version uses SQLAlchemy models.
    
    Args:
        period_id: ID of the reconciliation period to match
        
    Returns:
        MatchingResult with counts and statistics
    """
    from storsafe_app.db import db
    from storsafe_app.db.models import (
        BankTransaction, YardiTransaction, Match, 
        MatchBankTransaction, MatchYardiTransaction
    )
    
    result = MatchingResult()
    
    # Clear any existing matches for this period
    Match.query.filter_by(period_id=period_id).delete()
    db.session.commit()
    
    # Load bank transactions
    bank_rows = BankTransaction.query.filter_by(period_id=period_id).order_by(
        BankTransaction.date, BankTransaction.id
    ).all()
    
    # Load yardi transactions
    yardi_rows = YardiTransaction.query.filter_by(period_id=period_id).order_by(
        YardiTransaction.date, YardiTransaction.id
    ).all()
    
    result.bank_total = len(bank_rows)
    result.yardi_total = len(yardi_rows)
    
    if not bank_rows or not yardi_rows:
        logger.info(f"Period {period_id}: One or both sides empty. Bank={len(bank_rows)}, Yardi={len(yardi_rows)}")
        result.unmatched_bank = len(bank_rows)
        result.unmatched_yardi = len(yardi_rows)
        return result
    
    # Normalize data into dictionaries
    bank_norm = _normalize_transactions_orm(bank_rows, "bank")
    yardi_norm = _normalize_transactions_orm(yardi_rows, "yardi")
    
    # Track what's been matched
    matched_bank: Set[int] = set()  # bank db IDs
    matched_yardi: Set[int] = set()  # yardi db IDs
    
    # Results storage: list of (pass_name, match_type, bank_ids, yardi_ids)
    all_matches: List[Tuple[str, str, List[int], List[int]]] = []
    
    # Build indices for efficient lookup
    indices = _build_indices(bank_norm, yardi_norm)
    
    # Run all passes
    result.pass1_matches = _run_pass1(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches)
    result.pass2_matches = _run_pass2(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches)
    result.pass3_matches = _run_pass3(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches, day_tolerance=3)
    result.pass4_matches = _run_pass4(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches, day_tolerance=7)
    
    pass5_bank, pass5_yardi = _run_pass5(bank_norm, yardi_norm, matched_bank, matched_yardi, all_matches)
    result.pass5_bank_matches = pass5_bank
    result.pass5_yardi_matches = pass5_yardi
    
    result.pass6_matches = _run_pass6(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches)
    result.pass7_suggestions = _run_pass7(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches)
    
    # Save all matches to database
    _save_matches_to_db_orm(period_id, all_matches)
    db.session.commit()
    
    # Calculate unmatched counts
    result.unmatched_bank = len(bank_norm) - len(matched_bank)
    result.unmatched_yardi = len(yardi_norm) - len(matched_yardi)
    
    logger.info(
        f"Period {period_id} matching complete: "
        f"PASS1={result.pass1_matches}, PASS2={result.pass2_matches}, "
        f"PASS3={result.pass3_matches}, PASS4={result.pass4_matches}, "
        f"PASS5(bank)={result.pass5_bank_matches}, PASS5(yardi)={result.pass5_yardi_matches}, "
        f"PASS6={result.pass6_matches}, PASS7={result.pass7_suggestions}"
    )
    logger.info(
        f"Period {period_id} totals: "
        f"{result.total_matched} matched, "
        f"{result.unmatched_bank} unmatched bank, "
        f"{result.unmatched_yardi} unmatched yardi"
    )
    
    return result


def _normalize_transactions_orm(rows: List, source: str) -> List[Dict]:
    """
    Normalize ORM transaction objects into dictionaries for matching.
    
    Args:
        rows: List of ORM objects (BankTransaction or YardiTransaction)
        source: 'bank' or 'yardi'
        
    Returns:
        List of normalized transaction dictionaries
    """
    normalized = []
    for row in rows:
        # Parse date
        date_val = row.date
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
            "id": row.id,
            "date": date_obj,
            "txid": (row.transaction_id or "").strip(),
            "desc": (row.description or "").strip(),
            "amt": row.amount,
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
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime.combine(dt, datetime.min.time())
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _build_indices(bank_norm: List[Dict], yardi_norm: List[Dict]) -> Dict:
    """Build lookup indices for efficient matching."""
    indices = {
        "yardi_by_txid": {},
        "yardi_by_amt_date": {},
        "yardi_by_amt": {},
        "bank_by_amt": {},
    }
    
    for idx, y in enumerate(yardi_norm):
        if y["txid"]:
            indices["yardi_by_txid"].setdefault(y["txid"], []).append(idx)
        
        if y["amt"] is not None and y["date"] is not None:
            key = (_cents(y["amt"]), _normalize_date(y["date"]))
            indices["yardi_by_amt_date"].setdefault(key, []).append(idx)
        
        if y["amt"] is not None:
            indices["yardi_by_amt"].setdefault(_cents(y["amt"]), []).append(idx)
    
    for idx, b in enumerate(bank_norm):
        if b["amt"] is not None:
            indices["bank_by_amt"].setdefault(_cents(b["amt"]), []).append(idx)
    
    return indices


def _run_pass1(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches) -> int:
    """PASS 1: Match by Property + Transaction ID + Amount (strict 1:1)"""
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if not b["txid"] or b["amt"] is None:
            continue
        
        candidates = indices["yardi_by_txid"].get(b["txid"], [])
        
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
        
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 1", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass2(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches) -> int:
    """PASS 2: Match by Property + Date + Amount (strict 1:1)"""
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        key = (_cents(b["amt"]), _normalize_date(b["date"]))
        candidates = indices["yardi_by_amt_date"].get(key, [])
        
        filtered = [y_idx for y_idx in candidates if yardi_norm[y_idx]["id"] not in matched_yardi]
        
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 2", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass3(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches, day_tolerance=3) -> int:
    """PASS 3: Match by Property + Amount + Date within ±N days (strict 1:1)"""
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        candidates = indices["yardi_by_amt"].get(_cents(b["amt"]), [])
        
        filtered = []
        for y_idx in candidates:
            y = yardi_norm[y_idx]
            if y["id"] in matched_yardi:
                continue
            if y["date"] is None:
                continue
            b_date = _normalize_date(b["date"])
            y_date = _normalize_date(y["date"])
            if b_date and y_date:
                day_diff = abs((b_date - y_date).days)
                if day_diff <= day_tolerance:
                    filtered.append(y_idx)
        
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 3", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass4(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches, day_tolerance=7) -> int:
    """PASS 4: Same as PASS 3 but with wider date tolerance."""
    count = 0
    
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        
        candidates = indices["yardi_by_amt"].get(_cents(b["amt"]), [])
        
        filtered = []
        for y_idx in candidates:
            y = yardi_norm[y_idx]
            if y["id"] in matched_yardi:
                continue
            if y["date"] is None:
                continue
            b_date = _normalize_date(b["date"])
            y_date = _normalize_date(y["date"])
            if b_date and y_date:
                day_diff = abs((b_date - y_date).days)
                if day_diff <= day_tolerance:
                    filtered.append(y_idx)
        
        if len(filtered) == 1:
            y_idx = filtered[0]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 4", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass5(bank_norm, yardi_norm, matched_bank, matched_yardi, all_matches) -> Tuple[int, int]:
    """PASS 5: Same-side reversals (Bank↔Bank or Yardi↔Yardi)"""
    bank_count = 0
    yardi_count = 0
    
    # Bank↔Bank reversals
    bank_by_date_abs_amt: Dict[Tuple, List[int]] = {}
    for b_idx, b in enumerate(bank_norm):
        if b["id"] in matched_bank:
            continue
        if b["amt"] is None or b["date"] is None:
            continue
        key = (_normalize_date(b["date"]), abs(_cents(b["amt"])))
        bank_by_date_abs_amt.setdefault(key, []).append(b_idx)
    
    matched_bank_pass5: Set[int] = set()
    for key, bank_indices in bank_by_date_abs_amt.items():
        if len(bank_indices) < 2:
            continue
        
        positive = [idx for idx in bank_indices if bank_norm[idx]["amt"] > 0 and bank_norm[idx]["id"] not in matched_bank_pass5]
        negative = [idx for idx in bank_indices if bank_norm[idx]["amt"] < 0 and bank_norm[idx]["id"] not in matched_bank_pass5]
        
        for pos_idx, neg_idx in zip(positive, negative):
            pos_id = bank_norm[pos_idx]["id"]
            neg_id = bank_norm[neg_idx]["id"]
            
            matched_bank.add(pos_id)
            matched_bank.add(neg_id)
            matched_bank_pass5.add(pos_id)
            matched_bank_pass5.add(neg_id)
            
            all_matches.append(("PASS 5", "bank_bank", [neg_id, pos_id], []))
            bank_count += 1
    
    # Yardi↔Yardi reversals
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


def _run_pass6(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches) -> int:
    """PASS 6: Match by Property + Amount (exact) - only if counts match perfectly"""
    count = 0
    
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
    
    common_amounts = set(bank_by_amt.keys()) & set(yardi_by_amt.keys())
    
    for amt in common_amounts:
        bank_indices = bank_by_amt[amt]
        yardi_indices = yardi_by_amt[amt]
        
        if len(bank_indices) != len(yardi_indices):
            continue
        
        for b_idx, y_idx in zip(bank_indices, yardi_indices):
            b = bank_norm[b_idx]
            y = yardi_norm[y_idx]
            
            matched_bank.add(b["id"])
            matched_yardi.add(y["id"])
            all_matches.append(("PASS 6", "bank_yardi", [b["id"]], [y["id"]]))
            count += 1
    
    return count


def _run_pass7(bank_norm, yardi_norm, indices, matched_bank, matched_yardi, all_matches) -> int:
    """PASS 7: Suggested matches (incomplete pairing)"""
    count = 0
    
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
    
    common_amounts = set(bank_by_amt.keys()) & set(yardi_by_amt.keys())
    
    for amt in common_amounts:
        bank_indices = bank_by_amt[amt]
        yardi_indices = yardi_by_amt[amt]
        
        if len(bank_indices) == len(yardi_indices):
            continue
        
        bank_ids = [bank_norm[i]["id"] for i in bank_indices]
        yardi_ids = [yardi_norm[i]["id"] for i in yardi_indices]
        
        all_matches.append(("PASS 7", "suggestion", bank_ids, yardi_ids))
        count += 1
    
    return count


def _save_matches_to_db_orm(period_id: int, all_matches: List[Tuple[str, str, List[int], List[int]]]):
    """Save all matches to the database using SQLAlchemy."""
    from storsafe_app.db import db
    from storsafe_app.db.models import Match, MatchBankTransaction, MatchYardiTransaction
    
    for pass_name, match_type, bank_ids, yardi_ids in all_matches:
        notes = None
        if match_type == 'suggestion':
            notes = f"bank_ids:{','.join(map(str, bank_ids))}|yardi_ids:{','.join(map(str, yardi_ids))}"
        
        match = Match(
            period_id=period_id,
            match_pass=pass_name,
            match_type=match_type,
            notes=notes,
        )
        db.session.add(match)
        db.session.flush()  # Get the ID
        
        if match_type == 'suggestion':
            continue
        
        for bank_id in bank_ids:
            link = MatchBankTransaction(match_id=match.id, bank_transaction_id=bank_id)
            db.session.add(link)
        
        for yardi_id in yardi_ids:
            link = MatchYardiTransaction(match_id=match.id, yardi_transaction_id=yardi_id)
            db.session.add(link)
