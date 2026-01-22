#!/usr/bin/env python3
"""
Test script to verify adjustment features:
1. Adjustments tab appears on period detail page
2. Adjustment API endpoints work
3. Smart suggestions based on patterns
"""

import sys
from pathlib import Path

# Add project root to path
project_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_dir))

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://localhost:5000"


def test_adjustments_tab_exists():
    """Test that the Adjustments tab appears on period detail page."""
    print("\n[TEST] Adjustments tab exists...")
    
    try:
        # Get dashboard to find period IDs
        resp = requests.get(f"{BASE_URL}/dashboard/", timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        period_links = [a['href'] for a in soup.find_all('a') if '/dashboard/period/' in str(a.get('href', ''))]
        
        if not period_links:
            print("  [SKIP] No periods found - upload data first")
            return True
        
        period_url = period_links[0]
        if not period_url.startswith('http'):
            period_url = f"{BASE_URL}{period_url}"
        
        resp = requests.get(period_url, timeout=5)
        html = resp.text
        
        # Check for Adjustments tab
        has_adjustments_tab = "activeTab === 'adjustments'" in html
        has_adjustments_button = "Adjustments (" in html
        
        if has_adjustments_tab and has_adjustments_button:
            print("  [OK] Adjustments tab found")
            return True
        else:
            print("  [FAIL] Adjustments tab not found")
            print(f"    - activeTab === 'adjustments': {has_adjustments_tab}")
            print(f"    - Adjustments button: {has_adjustments_button}")
            return False
            
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def test_adjustments_section_structure():
    """Test that the Adjustments section has proper structure."""
    print("\n[TEST] Adjustments section structure...")
    
    try:
        resp = requests.get(f"{BASE_URL}/dashboard/", timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        period_links = [a['href'] for a in soup.find_all('a') if '/dashboard/period/' in str(a.get('href', ''))]
        
        if not period_links:
            print("  [SKIP] No periods found - upload data first")
            return True
        
        period_url = period_links[0]
        if not period_url.startswith('http'):
            period_url = f"{BASE_URL}{period_url}"
        
        resp = requests.get(period_url, timeout=5)
        html = resp.text
        
        # Check for key elements
        checks = [
            ("Adjustment Entries heading", "Adjustment Entries" in html),
            ("Reconciling items text", "Reconciling items" in html),
            ("addAdjustment function", "addAdjustment" in html),
            ("deleteAdjustment function", "deleteAdjustment" in html),
            ("addSelectedAsAdjustments function", "addSelectedAsAdjustments" in html),
            ("Mark as Adjustment button", "Mark as Adjustment" in html),
        ]
        
        all_passed = True
        for name, passed in checks:
            if passed:
                print(f"  [OK] {name}")
            else:
                print(f"  [FAIL] {name} not found")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def test_adjustments_api_endpoint():
    """Test the adjustments API endpoint."""
    print("\n[TEST] Adjustments API endpoint...")
    
    try:
        # First find a period
        resp = requests.get(f"{BASE_URL}/dashboard/", timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        period_links = [a['href'] for a in soup.find_all('a') if '/dashboard/period/' in str(a.get('href', ''))]
        
        if not period_links:
            print("  [SKIP] No periods found - upload data first")
            return True
        
        # Extract period ID from URL
        period_url = period_links[0]
        period_id = period_url.split('/')[-1]
        
        # Test the adjustments API
        resp = requests.get(f"{BASE_URL}/adjustments/period/{period_id}", timeout=5)
        
        if resp.status_code != 200:
            print(f"  [FAIL] API returned {resp.status_code}")
            return False
        
        data = resp.json()
        
        if "adjustments" in data and "suggestions" in data and "category_labels" in data:
            print("  [OK] API returns expected structure")
            print(f"      - {len(data['adjustments'])} adjustments")
            print(f"      - {len(data['suggestions'])} suggestions")
            print(f"      - {len(data['category_labels'])} category labels")
            return True
        else:
            print("  [FAIL] API response missing expected keys")
            return False
            
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def test_category_labels():
    """Test that category labels are properly defined."""
    print("\n[TEST] Category labels...")
    
    try:
        resp = requests.get(f"{BASE_URL}/dashboard/", timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        period_links = [a['href'] for a in soup.find_all('a') if '/dashboard/period/' in str(a.get('href', ''))]
        
        if not period_links:
            print("  [SKIP] No periods found - upload data first")
            return True
        
        period_url = period_links[0]
        period_id = period_url.split('/')[-1]
        
        resp = requests.get(f"{BASE_URL}/adjustments/period/{period_id}", timeout=5)
        data = resp.json()
        
        expected_categories = ['nsf_fee', 'overdraft_fee', 'bank_charge', 'interest_income', 'wire_fee', 'other']
        
        all_found = True
        for cat in expected_categories:
            if cat in data['category_labels']:
                print(f"  [OK] Category '{cat}' = '{data['category_labels'][cat]}'")
            else:
                print(f"  [FAIL] Category '{cat}' not found")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def test_differential_matching_support():
    """Test that differential matching is supported in the UI."""
    print("\n[TEST] Differential matching support...")
    
    try:
        resp = requests.get(f"{BASE_URL}/dashboard/", timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        period_links = [a['href'] for a in soup.find_all('a') if '/dashboard/period/' in str(a.get('href', ''))]
        
        if not period_links:
            print("  [SKIP] No periods found - upload data first")
            return True
        
        period_url = period_links[0]
        if not period_url.startswith('http'):
            period_url = f"{BASE_URL}{period_url}"
        
        resp = requests.get(period_url, timeout=5)
        html = resp.text
        
        # Check for differential adjustment prompt
        checks = [
            ("Differential check in createManualMatch", "create_differential" in html),
            ("Difference confirmation dialog", "The selected amounts don't match" in html),
        ]
        
        all_passed = True
        for name, passed in checks:
            if passed:
                print(f"  [OK] {name}")
            else:
                print(f"  [FAIL] {name} not found")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Adjustment Features")
    print("=" * 60)
    
    results = []
    
    results.append(("Adjustments tab exists", test_adjustments_tab_exists()))
    results.append(("Adjustments section structure", test_adjustments_section_structure()))
    results.append(("Adjustments API endpoint", test_adjustments_api_endpoint()))
    results.append(("Category labels", test_category_labels()))
    results.append(("Differential matching support", test_differential_matching_support()))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")
    
    print(f"\n  {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
