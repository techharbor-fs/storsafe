#!/usr/bin/env python3
"""
Bank Reconciliation Matching Test Suite

Comprehensive tests for the matching engine to catch bugs before production use.

Usage:
    # Run all tests with real data from Nov/Dec folders
    python test_matching.py
    
    # Run specific test
    python test_matching.py --test unit
    python test_matching.py --test integration
    python test_matching.py --test real_data
    
    # Verbose output
    python test_matching.py -v
"""

import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add project root to path for imports (tests folder is one level down)
sys.path.insert(0, str(Path(__file__).parent.parent))

from internal.matching.engine import (
    run_auto_matching, MatchingResult,
    _normalize_transactions, _cents, _build_indices,
    _run_pass1, _run_pass2, _run_pass3, _run_pass4, _run_pass5, _run_pass6, _run_pass7
)


class TestResult:
    """Result of a single test."""
    def __init__(self, name: str, passed: bool, message: str = "", details: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details
    
    def __str__(self):
        status = "[PASS]" if self.passed else "[FAIL]"
        s = f"{status}: {self.name}"
        if self.message:
            s += f"\n    {self.message}"
        if self.details and not self.passed:
            s += f"\n    Details: {self.details}"
        return s


class TestSuite:
    """Collection of test results."""
    def __init__(self, name: str):
        self.name = name
        self.results: List[TestResult] = []
    
    def add(self, result: TestResult):
        self.results.append(result)
    
    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)
    
    @property
    def total(self) -> int:
        return len(self.results)
    
    def print_summary(self):
        print(f"\n{'=' * 70}")
        print(f"Test Suite: {self.name}")
        print(f"{'=' * 70}")
        
        for r in self.results:
            print(r)
        
        print(f"\n{'-' * 70}")
        print(f"Total: {self.total}, Passed: {self.passed}, Failed: {self.failed}")
        
        if self.failed == 0:
            print("All tests passed!")
        else:
            print(f"FAILURES: {self.failed} test(s) failed")


def create_test_db() -> Tuple[sqlite3.Connection, Path]:
    """Create a temporary test database."""
    # Create temp file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Connect and create schema
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Read and execute schema
    schema_path = Path(__file__).parent.parent / "internal" / "database" / "schema.sql"
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    
    conn.commit()
    return conn, Path(db_path)


def cleanup_test_db(conn: sqlite3.Connection, db_path: Path):
    """Clean up test database."""
    conn.close()
    if db_path.exists():
        db_path.unlink()


def insert_test_property(conn: sqlite3.Connection, name: str = "Test Property") -> int:
    """Insert a test property and return its ID (or get existing)."""
    # Try to get existing first
    existing = conn.execute("SELECT id FROM properties WHERE name = ?", (name,)).fetchone()
    if existing:
        return existing["id"]
    
    cursor = conn.execute("INSERT INTO properties (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def insert_test_period(conn: sqlite3.Connection, property_id: int, year: int = 2025, month: int = 12) -> int:
    """Insert a test reconciliation period and return its ID."""
    cursor = conn.execute(
        "INSERT INTO reconciliation_periods (property_id, year, month) VALUES (?, ?, ?)",
        (property_id, year, month)
    )
    conn.commit()
    return cursor.lastrowid


def insert_bank_transaction(
    conn: sqlite3.Connection, period_id: int,
    date: str, txid: str, desc: str, amount: float, tx_type: str = "CHECK"
) -> int:
    """Insert a bank transaction and return its ID."""
    cursor = conn.execute("""
        INSERT INTO bank_transactions (period_id, date, transaction_id, description, amount, transaction_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (period_id, date, txid, desc, amount, tx_type))
    return cursor.lastrowid


def insert_yardi_transaction(
    conn: sqlite3.Connection, period_id: int,
    date: str, txid: str, desc: str, amount: float, source_type: str = "check"
) -> int:
    """Insert a Yardi transaction and return its ID."""
    cursor = conn.execute("""
        INSERT INTO yardi_transactions (period_id, date, transaction_id, description, amount, source_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (period_id, date, txid, desc, amount, source_type))
    return cursor.lastrowid


# =============================================================================
# UNIT TESTS - Test individual components
# =============================================================================

def test_cents_conversion(suite: TestSuite):
    """Test the _cents function for float-to-int conversion."""
    test_cases = [
        (100.00, 10000),
        (100.01, 10001),
        (100.99, 10099),
        (-500.50, -50050),
        (0.01, 1),
        (0.00, 0),
        (None, None),
    ]
    
    for amount, expected in test_cases:
        result = _cents(amount)
        passed = result == expected
        suite.add(TestResult(
            f"_cents({amount})",
            passed,
            f"Expected {expected}, got {result}" if not passed else ""
        ))


def test_pass1_exact_match(suite: TestSuite):
    """Test PASS 1: Exact match by Transaction ID + Amount."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # Insert matching transactions
        b1 = insert_bank_transaction(conn, period_id, "2025-12-01", "1001", "Check 1001", -500.00)
        y1 = insert_yardi_transaction(conn, period_id, "2025-12-01", "1001", "Check 1001", -500.00)
        
        conn.commit()
        
        result = run_auto_matching(conn, period_id)
        
        suite.add(TestResult(
            "PASS 1: Exact txid+amount match",
            result.pass1_matches == 1,
            f"Expected 1 match, got {result.pass1_matches}"
        ))
        
        # Verify the match was recorded
        matches = conn.execute("SELECT * FROM matches WHERE period_id = ?", (period_id,)).fetchall()
        suite.add(TestResult(
            "PASS 1: Match recorded in DB",
            len(matches) == 1 and matches[0]["match_pass"] == "PASS 1",
            f"Found {len(matches)} matches"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass1_no_match_different_amount(suite: TestSuite):
    """Test PASS 1: No match when amounts differ."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # Same txid but different amounts
        insert_bank_transaction(conn, period_id, "2025-12-01", "1001", "Check", -500.00)
        insert_yardi_transaction(conn, period_id, "2025-12-01", "1001", "Check", -600.00)
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        suite.add(TestResult(
            "PASS 1: No match with different amounts",
            result.pass1_matches == 0,
            f"Expected 0 matches, got {result.pass1_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass2_date_amount_match(suite: TestSuite):
    """Test PASS 2: Match by Date + Amount when txid is empty."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # No txid, but same date and amount
        insert_bank_transaction(conn, period_id, "2025-12-05", "", "ACH Payment", -250.00, "ACH")
        insert_yardi_transaction(conn, period_id, "2025-12-05", "", "ACH Payment", -250.00, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        suite.add(TestResult(
            "PASS 2: Date+Amount match",
            result.pass2_matches == 1,
            f"Expected 1 match, got {result.pass2_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass3_date_tolerance_3_days(suite: TestSuite):
    """Test PASS 3: Match with ±3 day date tolerance."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # 2 days apart - should match
        insert_bank_transaction(conn, period_id, "2025-12-05", "", "Payment", -300.00, "ACH")
        insert_yardi_transaction(conn, period_id, "2025-12-07", "", "Payment", -300.00, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        # Should match in PASS 3 (not PASS 2 because dates differ)
        suite.add(TestResult(
            "PASS 3: 2-day difference matches",
            result.pass3_matches == 1,
            f"Expected 1 PASS 3 match, got {result.pass3_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass3_no_match_4_days(suite: TestSuite):
    """Test PASS 3: No match when dates are 4 days apart."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # 4 days apart - should NOT match in PASS 3
        insert_bank_transaction(conn, period_id, "2025-12-01", "", "Payment", -300.00, "ACH")
        insert_yardi_transaction(conn, period_id, "2025-12-05", "", "Payment", -300.00, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        suite.add(TestResult(
            "PASS 3: 4-day difference does not match",
            result.pass3_matches == 0,
            f"Expected 0 PASS 3 matches, got {result.pass3_matches}"
        ))
        
        # But should match in PASS 4
        suite.add(TestResult(
            "PASS 4: 4-day difference matches",
            result.pass4_matches == 1,
            f"Expected 1 PASS 4 match, got {result.pass4_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass5_bank_reversal(suite: TestSuite):
    """Test PASS 5: Bank-to-Bank reversal matching."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # A payment and its reversal on the same date
        b1 = insert_bank_transaction(conn, period_id, "2025-12-10", "", "ACH Payment", -100.00, "ACH")
        b2 = insert_bank_transaction(conn, period_id, "2025-12-10", "", "ACH Reversal", 100.00, "ACH")
        
        # Also need at least one Yardi transaction for matching to run properly
        # (Otherwise the algorithm exits early if one side is empty)
        y1 = insert_yardi_transaction(conn, period_id, "2025-12-10", "", "Unrelated", -999.00, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        suite.add(TestResult(
            "PASS 5: Bank reversal pair matched",
            result.pass5_bank_matches == 1,
            f"Expected 1 bank reversal, got {result.pass5_bank_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass6_equal_counts(suite: TestSuite):
    """Test PASS 6: Match when counts are equal."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # Use a unique amount to avoid interference from other tests
        # 2 bank transactions with same amount, dates more than 7 days apart from yardi
        insert_bank_transaction(conn, period_id, "2025-11-01", "", "Payment A", -777.77, "ACH")
        insert_bank_transaction(conn, period_id, "2025-11-02", "", "Payment B", -777.77, "ACH")
        
        # 2 yardi transactions with same amount, dates more than 7 days apart from bank
        insert_yardi_transaction(conn, period_id, "2025-12-25", "", "Item A", -777.77, "other")
        insert_yardi_transaction(conn, period_id, "2025-12-26", "", "Item B", -777.77, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        # PASS 2/3/4 won't match (dates too far apart), but PASS 6 should
        suite.add(TestResult(
            "PASS 6: Equal counts matched",
            result.pass6_matches == 2,
            f"Expected 2 PASS 6 matches, got {result.pass6_matches}, "
            f"total matched: {result.total_matched}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_pass7_unequal_counts(suite: TestSuite):
    """Test PASS 7: Suggestions when counts differ."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # 3 bank transactions with same amount
        insert_bank_transaction(conn, period_id, "2025-12-01", "", "Payment A", -200.00, "ACH")
        insert_bank_transaction(conn, period_id, "2025-12-05", "", "Payment B", -200.00, "ACH")
        insert_bank_transaction(conn, period_id, "2025-12-10", "", "Payment C", -200.00, "ACH")
        
        # Only 2 yardi transactions with same amount
        insert_yardi_transaction(conn, period_id, "2025-11-20", "", "Item A", -200.00, "other")
        insert_yardi_transaction(conn, period_id, "2025-12-25", "", "Item B", -200.00, "other")
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        # Should have PASS 7 suggestion, not PASS 6 match
        suite.add(TestResult(
            "PASS 7: Unequal counts creates suggestion",
            result.pass7_suggestions > 0,
            f"Expected suggestions, got {result.pass7_suggestions}"
        ))
        
        suite.add(TestResult(
            "PASS 6: No matches with unequal counts",
            result.pass6_matches == 0,
            f"Expected 0 PASS 6 matches, got {result.pass6_matches}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_no_double_matching(suite: TestSuite):
    """Test that transactions aren't matched twice."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # One bank transaction
        insert_bank_transaction(conn, period_id, "2025-12-05", "1001", "Check", -500.00)
        
        # Two yardi transactions that could match
        insert_yardi_transaction(conn, period_id, "2025-12-05", "1001", "Check", -500.00)
        insert_yardi_transaction(conn, period_id, "2025-12-05", "1001", "Check Dup", -500.00)
        
        conn.commit()
        result = run_auto_matching(conn, period_id)
        
        # Should only match one (strict 1:1)
        suite.add(TestResult(
            "No double matching",
            result.total_matched == 0,  # PASS 1 requires exactly 1 candidate
            f"Expected 0 matches (ambiguous), got {result.total_matched}"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


def test_database_integrity(suite: TestSuite):
    """Test that database constraints are maintained."""
    conn, db_path = create_test_db()
    
    try:
        prop_id = insert_test_property(conn)
        period_id = insert_test_period(conn, prop_id)
        
        # Insert transactions
        insert_bank_transaction(conn, period_id, "2025-12-05", "1001", "Check", -500.00)
        insert_yardi_transaction(conn, period_id, "2025-12-05", "1001", "Check", -500.00)
        
        conn.commit()
        run_auto_matching(conn, period_id)
        
        # Verify foreign key integrity
        orphan_bank = conn.execute("""
            SELECT COUNT(*) FROM match_bank_transactions mbt
            WHERE NOT EXISTS (SELECT 1 FROM matches m WHERE m.id = mbt.match_id)
        """).fetchone()[0]
        
        orphan_yardi = conn.execute("""
            SELECT COUNT(*) FROM match_yardi_transactions myt
            WHERE NOT EXISTS (SELECT 1 FROM matches m WHERE m.id = myt.match_id)
        """).fetchone()[0]
        
        suite.add(TestResult(
            "DB Integrity: No orphan bank links",
            orphan_bank == 0,
            f"Found {orphan_bank} orphan bank transaction links"
        ))
        
        suite.add(TestResult(
            "DB Integrity: No orphan yardi links",
            orphan_yardi == 0,
            f"Found {orphan_yardi} orphan yardi transaction links"
        ))
        
    finally:
        cleanup_test_db(conn, db_path)


# =============================================================================
# INTEGRATION TESTS - Test with real data files
# =============================================================================

def test_real_data(suite: TestSuite, verbose: bool = False):
    """Test with real data from the Nov/Dec folders."""
    project_dir = Path(__file__).parent.parent
    
    # Find test data folders
    test_folders = [
        ("11. Nov", "2025-11_Bank_Rec_Madison.xlsx", "--- SS of Madison_Notre Dame 11.30.2025.pdf"),
        ("12. Dec", "Bank_Rec.xlsx", "--- SS of Madison_Notre Dame 12.31.2025.pdf"),
    ]
    
    from internal.parsers import get_parser_for_pdf, extract_yardi_from_excel
    
    conn, db_path = create_test_db()
    
    try:
        for folder_name, excel_name, pdf_name in test_folders:
            folder = project_dir / folder_name
            
            if not folder.exists():
                suite.add(TestResult(
                    f"Real data: {folder_name}",
                    False,
                    f"Folder not found: {folder}"
                ))
                continue
            
            # Find files
            excel_path = folder / excel_name
            pdf_path = folder / pdf_name
            
            # Try alternate names
            if not excel_path.exists():
                excels = list(folder.glob("*Bank_Rec*.xlsx")) + list(folder.glob("*_Bank_Rec_*.xlsx"))
                if excels:
                    excel_path = excels[0]
            
            if not pdf_path.exists():
                pdfs = list(folder.glob("*.pdf"))
                if pdfs:
                    pdf_path = pdfs[0]
            
            if not excel_path.exists():
                suite.add(TestResult(
                    f"Real data: {folder_name} - Excel",
                    False,
                    f"Excel file not found in {folder}"
                ))
                continue
            
            if not pdf_path.exists():
                suite.add(TestResult(
                    f"Real data: {folder_name} - PDF",
                    False,
                    f"PDF file not found in {folder}"
                ))
                continue
            
            # Create period
            prop_id = insert_test_property(conn, "Madison")
            year = 2025
            month = 11 if "Nov" in folder_name else 12
            period_id = insert_test_period(conn, prop_id, year, month)
            
            # Parse and insert bank transactions
            try:
                parser = get_parser_for_pdf(pdf_path)
                if parser:
                    bank_txns = parser.parse(pdf_path)
                    for txn in bank_txns:
                        insert_bank_transaction(
                            conn, period_id,
                            txn.date.strftime("%Y-%m-%d"),
                            txn.transaction_id,
                            txn.description,
                            txn.amount,
                            txn.transaction_type
                        )
                    
                    suite.add(TestResult(
                        f"Real data: {folder_name} - Parse bank PDF",
                        len(bank_txns) > 0,
                        f"Parsed {len(bank_txns)} bank transactions"
                    ))
                else:
                    suite.add(TestResult(
                        f"Real data: {folder_name} - Parse bank PDF",
                        False,
                        "No parser found for PDF"
                    ))
                    continue
            except Exception as e:
                suite.add(TestResult(
                    f"Real data: {folder_name} - Parse bank PDF",
                    False,
                    f"Error: {e}"
                ))
                continue
            
            # Parse and insert Yardi transactions
            try:
                yardi_txns, analysis = extract_yardi_from_excel(excel_path)
                for txn in yardi_txns:
                    insert_yardi_transaction(
                        conn, period_id,
                        txn["date"],
                        txn["transaction_id"],
                        txn["description"],
                        txn["amount"],
                        txn["source_type"]
                    )
                
                suite.add(TestResult(
                    f"Real data: {folder_name} - Parse Yardi Excel",
                    len(yardi_txns) > 0,
                    f"Parsed {len(yardi_txns)} Yardi transactions"
                ))
            except Exception as e:
                suite.add(TestResult(
                    f"Real data: {folder_name} - Parse Yardi Excel",
                    False,
                    f"Error: {e}"
                ))
                continue
            
            conn.commit()
            
            # Run matching
            try:
                result = run_auto_matching(conn, period_id)
                
                suite.add(TestResult(
                    f"Real data: {folder_name} - Matching runs",
                    True,
                    f"Bank: {result.bank_total}, Yardi: {result.yardi_total}, "
                    f"Matched: {result.total_matched}, "
                    f"Unmatched: {result.unmatched_bank}B/{result.unmatched_yardi}Y"
                ))
                
                # Check that we got some matches
                suite.add(TestResult(
                    f"Real data: {folder_name} - Has matches",
                    result.total_matched > 0,
                    f"Total matched: {result.total_matched}"
                ))
                
                if verbose:
                    print(f"\n  {folder_name} Matching Results:")
                    print(f"    PASS 1: {result.pass1_matches}")
                    print(f"    PASS 2: {result.pass2_matches}")
                    print(f"    PASS 3: {result.pass3_matches}")
                    print(f"    PASS 4: {result.pass4_matches}")
                    print(f"    PASS 5 (bank): {result.pass5_bank_matches}")
                    print(f"    PASS 5 (yardi): {result.pass5_yardi_matches}")
                    print(f"    PASS 6: {result.pass6_matches}")
                    print(f"    PASS 7 suggestions: {result.pass7_suggestions}")
                    
            except Exception as e:
                suite.add(TestResult(
                    f"Real data: {folder_name} - Matching",
                    False,
                    f"Error: {e}"
                ))
                
    finally:
        cleanup_test_db(conn, db_path)


# =============================================================================
# MAIN
# =============================================================================

def run_unit_tests(verbose: bool = False) -> TestSuite:
    """Run all unit tests."""
    suite = TestSuite("Unit Tests")
    
    test_cents_conversion(suite)
    test_pass1_exact_match(suite)
    test_pass1_no_match_different_amount(suite)
    test_pass2_date_amount_match(suite)
    test_pass3_date_tolerance_3_days(suite)
    test_pass3_no_match_4_days(suite)
    test_pass5_bank_reversal(suite)
    test_pass6_equal_counts(suite)
    test_pass7_unequal_counts(suite)
    test_no_double_matching(suite)
    test_database_integrity(suite)
    
    return suite


def run_integration_tests(verbose: bool = False) -> TestSuite:
    """Run integration tests with real data."""
    suite = TestSuite("Integration Tests (Real Data)")
    test_real_data(suite, verbose)
    return suite


def main():
    parser = argparse.ArgumentParser(description="Bank Reconciliation Matching Test Suite")
    parser.add_argument(
        "--test",
        choices=["all", "unit", "integration", "real_data"],
        default="all",
        help="Which tests to run"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("Bank Reconciliation Matching Test Suite")
    print("=" * 70)
    
    all_passed = True
    
    if args.test in ("all", "unit"):
        unit_suite = run_unit_tests(args.verbose)
        unit_suite.print_summary()
        if unit_suite.failed > 0:
            all_passed = False
    
    if args.test in ("all", "integration", "real_data"):
        int_suite = run_integration_tests(args.verbose)
        int_suite.print_summary()
        if int_suite.failed > 0:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED - Review output above")
    print("=" * 70)
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
