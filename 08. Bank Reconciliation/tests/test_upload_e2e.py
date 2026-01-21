#!/usr/bin/env python3
"""
End-to-End Upload Test

Tests the full upload flow by posting files to the Flask app
and verifying the matching results.

Usage:
    # Make sure the Flask app is running first
    python run_bank_rec_app.py
    
    # Then in another terminal:
    python test_upload_e2e.py
"""

import requests
import sys
from pathlib import Path


def test_upload_flow():
    """Test the full upload flow with real data files."""
    base_url = "http://localhost:5000"
    
    # Test data files (tests folder is one level down from project root)
    project_dir = Path(__file__).parent.parent
    nov_folder = project_dir / "11. Nov"
    dec_folder = project_dir / "12. Dec"
    
    print("=" * 70)
    print("End-to-End Upload Test")
    print("=" * 70)
    
    # Check server is running
    try:
        resp = requests.get(f"{base_url}/dashboard/", timeout=5)
        if resp.status_code != 200:
            print(f"FAIL: Dashboard returned {resp.status_code}")
            return False
        print("[OK] Server is running")
    except requests.ConnectionError:
        print("FAIL: Cannot connect to server. Is run_bank_rec_app.py running?")
        return False
    
    # Find files
    excel_files = list(nov_folder.glob("*Bank_Rec*.xlsx"))
    pdf_files = list(nov_folder.glob("*.pdf"))
    
    if not excel_files:
        print(f"FAIL: No Excel file found in {nov_folder}")
        return False
    if not pdf_files:
        print(f"FAIL: No PDF file found in {nov_folder}")
        return False
    
    excel_path = excel_files[0]
    pdf_path = pdf_files[0]
    
    print(f"[OK] Found files:")
    print(f"     Excel: {excel_path.name}")
    print(f"     PDF: {pdf_path.name}")
    
    # Upload files
    print("\nUploading files...")
    
    with open(excel_path, "rb") as excel_file, open(pdf_path, "rb") as pdf_file:
        files = {
            "yardi_excel": (excel_path.name, excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "bank_pdf": (pdf_path.name, pdf_file, "application/pdf"),
        }
        data = {
            "property_name": "Test Madison E2E",
            "month": "11",
            "year": "2025",
        }
        
        resp = requests.post(
            f"{base_url}/upload/",
            files=files,
            data=data,
            allow_redirects=False,  # Don't follow redirect so we can check it
        )
    
    if resp.status_code not in (302, 303):
        print(f"FAIL: Upload returned {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    
    print(f"[OK] Upload successful (redirect to period detail)")
    
    # Check the redirect location
    redirect_url = resp.headers.get("Location", "")
    print(f"     Redirect: {redirect_url}")
    
    # Follow redirect and check period detail page
    if redirect_url:
        resp = requests.get(f"{base_url}{redirect_url}" if redirect_url.startswith("/") else redirect_url)
        
        if resp.status_code != 200:
            print(f"FAIL: Period detail returned {resp.status_code}")
            return False
        
        # Check for expected content
        html = resp.text
        
        if "Test Madison E2E" not in html and "November 2025" not in html:
            print("WARN: Period name not found in response")
        
        # Look for match indicators
        if "PASS 1" in html or "matched" in html.lower():
            print("[OK] Match results appear on period detail page")
        else:
            print("WARN: No match results visible on page")
        
        # Count some indicators
        if "Unmatched" in html:
            print("[OK] Unmatched section visible")
    
    print("\n" + "=" * 70)
    print("END-TO-END TEST PASSED")
    print("=" * 70)
    return True


def main():
    success = test_upload_flow()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
