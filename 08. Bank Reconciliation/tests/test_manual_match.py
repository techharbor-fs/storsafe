#!/usr/bin/env python3
"""
Test manual matching API endpoint.

Usage:
    # Make sure the Flask app is running first
    python run_bank_rec_app.py
    
    # Then run this test
    python test_manual_match.py
"""

import json
import requests
import sqlite3
from pathlib import Path


def get_unmatched_ids():
    """Get IDs of unmatched transactions from database."""
    db_path = Path(__file__).parent.parent / 'data' / 'bank_rec.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Get unmatched bank
    unmatched_bank = conn.execute("""
        SELECT bt.id, bt.amount
        FROM bank_transactions bt
        WHERE bt.period_id = 1
        AND NOT EXISTS (
            SELECT 1 FROM match_bank_transactions mbt WHERE mbt.bank_transaction_id = bt.id
        )
        LIMIT 2
    """).fetchall()
    
    # Get unmatched yardi
    unmatched_yardi = conn.execute("""
        SELECT yt.id, yt.amount
        FROM yardi_transactions yt
        WHERE yt.period_id = 1
        AND NOT EXISTS (
            SELECT 1 FROM match_yardi_transactions myt WHERE myt.yardi_transaction_id = yt.id
        )
        LIMIT 2
    """).fetchall()
    
    conn.close()
    return unmatched_bank, unmatched_yardi


def test_manual_match():
    """Test the manual matching API."""
    base_url = "http://localhost:5000"
    
    print("=" * 70)
    print("Manual Matching API Test")
    print("=" * 70)
    
    # Check server is running
    try:
        resp = requests.get(f"{base_url}/dashboard/", timeout=5)
        if resp.status_code != 200:
            print(f"FAIL: Server not responding properly")
            return False
        print("[OK] Server is running")
    except requests.ConnectionError:
        print("FAIL: Cannot connect to server")
        return False
    
    # Get unmatched transaction IDs
    unmatched_bank, unmatched_yardi = get_unmatched_ids()
    
    if len(unmatched_bank) < 1 or len(unmatched_yardi) < 1:
        print("SKIP: Not enough unmatched transactions to test")
        return True
    
    bank_ids = [row["id"] for row in unmatched_bank]
    yardi_ids = [row["id"] for row in unmatched_yardi]
    
    print(f"[OK] Found unmatched: {len(bank_ids)} bank, {len(yardi_ids)} yardi")
    print(f"     Bank IDs: {bank_ids}")
    print(f"     Yardi IDs: {yardi_ids}")
    
    # Test 1: Valid manual match
    print("\nTest 1: Create manual match...")
    resp = requests.post(
        f"{base_url}/dashboard/period/1/match",
        json={"bank_ids": bank_ids[:1], "yardi_ids": yardi_ids[:1]},
        headers={"Content-Type": "application/json"}
    )
    
    if resp.status_code != 200:
        print(f"FAIL: Status {resp.status_code}")
        print(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    if not data.get("success"):
        print(f"FAIL: {data.get('error')}")
        return False
    
    print(f"[OK] Created match ID: {data.get('match_id')}")
    
    # Test 2: Try to match already matched transaction
    print("\nTest 2: Reject already matched transaction...")
    resp = requests.post(
        f"{base_url}/dashboard/period/1/match",
        json={"bank_ids": bank_ids[:1], "yardi_ids": yardi_ids[1:2]},
        headers={"Content-Type": "application/json"}
    )
    
    data = resp.json()
    if data.get("success"):
        print("FAIL: Should have rejected already matched transaction")
        return False
    
    print(f"[OK] Correctly rejected: {data.get('error')}")
    
    # Test 3: Empty selection
    print("\nTest 3: Reject empty selection...")
    resp = requests.post(
        f"{base_url}/dashboard/period/1/match",
        json={"bank_ids": [], "yardi_ids": []},
        headers={"Content-Type": "application/json"}
    )
    
    data = resp.json()
    if data.get("success"):
        print("FAIL: Should have rejected empty selection")
        return False
    
    print(f"[OK] Correctly rejected: {data.get('error')}")
    
    print("\n" + "=" * 70)
    print("ALL API TESTS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    import sys
    success = test_manual_match()
    sys.exit(0 if success else 1)
