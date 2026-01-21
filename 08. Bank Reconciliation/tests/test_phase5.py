#!/usr/bin/env python3
"""
Phase 5 Feature Tests

Tests for:
- Re-run auto-matching
- Export to Excel
- Toggle period status

Usage:
    python run_bank_rec_app.py  # In one terminal
    python test_phase5.py       # In another terminal
"""

import requests
import sys


def test_phase5_features():
    """Test all Phase 5 features."""
    base_url = "http://localhost:5000"
    
    print("=" * 70)
    print("Phase 5 Feature Tests")
    print("=" * 70)
    
    # Check server
    try:
        resp = requests.get(f"{base_url}/dashboard/", timeout=5)
        if resp.status_code != 200:
            print("FAIL: Server not responding")
            return False
        print("[OK] Server is running")
    except requests.ConnectionError:
        print("FAIL: Cannot connect to server")
        return False
    
    # Test 1: Period detail page has action buttons
    print("\nTest 1: Period detail page...")
    resp = requests.get(f"{base_url}/dashboard/period/1")
    if resp.status_code != 200:
        print(f"FAIL: Period detail returned {resp.status_code}")
        return False
    
    html = resp.text
    checks = [
        ("Re-run Auto-Match button", "Re-run Auto-Match" in html),
        ("Export Excel button", "Export Excel" in html),
        ("Mark Complete/Reopen button", "Mark Complete" in html or "Reopen" in html),
        ("Filter inputs", "Filter bank transactions" in html),
    ]
    
    for name, passed in checks:
        if passed:
            print(f"[OK] {name}")
        else:
            print(f"FAIL: {name}")
            return False
    
    # Test 2: Export Excel
    print("\nTest 2: Export Excel...")
    resp = requests.get(f"{base_url}/dashboard/period/1/export")
    if resp.status_code != 200:
        print(f"FAIL: Export returned {resp.status_code}")
        return False
    
    content_type = resp.headers.get("Content-Type", "")
    if "spreadsheet" not in content_type:
        print(f"FAIL: Wrong content type: {content_type}")
        return False
    
    content_disposition = resp.headers.get("Content-Disposition", "")
    if "Bank_Rec_" not in content_disposition:
        print(f"FAIL: Wrong filename: {content_disposition}")
        return False
    
    print(f"[OK] Export Excel works ({len(resp.content)} bytes)")
    
    # Test 3: Toggle status (mark complete)
    print("\nTest 3: Toggle status (mark complete)...")
    resp = requests.post(f"{base_url}/dashboard/period/1/toggle-status", allow_redirects=False)
    if resp.status_code not in (302, 303):
        print(f"FAIL: Toggle status returned {resp.status_code}")
        return False
    print("[OK] Toggle status works")
    
    # Check it's now completed
    resp = requests.get(f"{base_url}/dashboard/period/1")
    if "Completed" not in resp.text:
        print("FAIL: Status not updated to Completed")
        return False
    print("[OK] Status changed to Completed")
    
    # Test 4: Toggle back (reopen)
    print("\nTest 4: Toggle status (reopen)...")
    resp = requests.post(f"{base_url}/dashboard/period/1/toggle-status", allow_redirects=False)
    if resp.status_code not in (302, 303):
        print(f"FAIL: Toggle status returned {resp.status_code}")
        return False
    
    resp = requests.get(f"{base_url}/dashboard/period/1")
    if "In Progress" not in resp.text:
        print("FAIL: Status not updated to In Progress")
        return False
    print("[OK] Status changed back to In Progress")
    
    # Test 5: Re-run matching
    print("\nTest 5: Re-run auto-matching...")
    resp = requests.post(f"{base_url}/dashboard/period/1/rerun-matching", allow_redirects=False)
    if resp.status_code not in (302, 303):
        print(f"FAIL: Re-run matching returned {resp.status_code}")
        return False
    print("[OK] Re-run matching works")
    
    print("\n" + "=" * 70)
    print("ALL PHASE 5 TESTS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = test_phase5_features()
    sys.exit(0 if success else 1)
