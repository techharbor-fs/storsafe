"""Fetch property-specific cash account mappings from Google Sheets.

Reads the Account Code Reconciliation spreadsheet and extracts cash description -> Yardi code
mappings for each property. Outputs a JSON file that the transform script uses.

Usage:
    python fetch_cash_account_mappings.py [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import gspread

SHEET_ID = "1DxP8RW3Q_e9kTqGkFnqCMwsaUKDOli_-Mg42YYuKI3I"

# Cash-related descriptions we care about
CASH_DESCRIPTIONS = {
    "cash",
    "checks",
    "ach",
    "money order",
    "credit card - visa",
    "credit card - master card",
    "credit card - mastercard",
    "credit card - american express",
    "credit card - discover",
    "credit card - other",
    "refund checks",
}

# Tabs that are NOT property-specific (skip these)
GLOBAL_TABS = {
    "edge",
    "edge-normalized", 
    "yardi-tb",
    "upload summary",
    "property codes",
    "account code mapping",
    "sheet7",
    "yardi_import_compiled__2025-12",
    "yardi_import_jay__2025-12",
    "cash_account_corrections__2025-12",
}


def connect_sheet() -> gspread.Spreadsheet:
    """Connect to the Account Code Reconciliation spreadsheet."""
    # Check environment variable first (JSON string)
    service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        temp_json_path = Path(tempfile.gettempdir()) / "service_account.json"
        temp_json_path.write_text(json.dumps(json.loads(service_account_json)), encoding="utf-8")
        gc = gspread.service_account(filename=str(temp_json_path))
        return gc.open_by_key(SHEET_ID)
    
    # Check environment variable (file path)
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("SERVICE_ACCOUNT_FILE")
    if env_path and Path(env_path).exists():
        gc = gspread.service_account(filename=env_path)
        return gc.open_by_key(SHEET_ID)
    
    # Try common locations
    common_paths = [
        Path(__file__).parent / "service-account.json",
        Path(__file__).parent.parent / "service-account.json",
        Path(__file__).resolve().parents[2] / "service-account.json",
        Path.home() / ".config" / "gspread" / "service_account.json",
        Path.home() / "service_account.json",
        Path("service_account.json"),
        Path("service-account.json"),
    ]
    for p in common_paths:
        if p.exists():
            print(f"  Using service account: {p}")
            gc = gspread.service_account(filename=str(p))
            return gc.open_by_key(SHEET_ID)
    
    # Try default gspread service account location
    try:
        gc = gspread.service_account()
        return gc.open_by_key(SHEET_ID)
    except Exception:
        pass
    
    raise RuntimeError(
        f"Missing Google service account credentials. Set SERVICE_ACCOUNT_JSON or "
        f"GOOGLE_APPLICATION_CREDENTIALS environment variable, or place service_account.json "
        f"in one of: {[str(p) for p in common_paths]}"
    )


def extract_cash_mappings_from_tab(ws: gspread.Worksheet) -> dict[str, str]:
    """Extract Description -> Yardi Code mappings for cash-related rows.
    
    Expected columns in the property tabs:
    A: Edge Code (internal)
    B: Category
    C: Subcategory  
    D: Description
    E: Yardi Code
    """
    mappings: dict[str, str] = {}
    
    try:
        # Get columns A through E, starting from row 2 (skip header)
        values = ws.get("A2:E200")
    except Exception as e:
        print(f"  ⚠️ Could not read tab: {e}")
        return mappings
    
    for row in values:
        # Pad row to 5 columns
        while len(row) < 5:
            row.append("")
        
        edge_code, category, subcategory, description, yardi_code = [
            str(cell).strip() if cell else "" for cell in row
        ]
        
        # Skip empty rows
        if not description or not yardi_code:
            continue
        
        # Check if this is a cash-related description
        desc_lower = description.lower()
        if desc_lower in CASH_DESCRIPTIONS:
            mappings[description] = yardi_code
    
    return mappings


def get_property_tabs(sh: gspread.Spreadsheet) -> list[str]:
    """Get list of property tab names (excluding global tabs)."""
    all_tabs = [ws.title for ws in sh.worksheets()]
    property_tabs = [
        tab for tab in all_tabs 
        if tab.lower() not in GLOBAL_TABS
    ]
    return property_tabs


def fetch_all_cash_mappings(sh: gspread.Spreadsheet, delay: float = 1.5) -> dict[str, dict[str, str]]:
    """Fetch cash account mappings for all properties.
    
    Args:
        sh: Google Spreadsheet object
        delay: Seconds to wait between API calls to avoid rate limiting
    
    Returns:
        Dict mapping property_code -> {description: yardi_code}
    """
    import time
    
    all_mappings: dict[str, dict[str, str]] = {}
    
    property_tabs = get_property_tabs(sh)
    print(f"Found {len(property_tabs)} property tabs")
    
    for i, tab_name in enumerate(property_tabs, 1):
        print(f"  [{i}/{len(property_tabs)}] Processing: {tab_name}")
        try:
            ws = sh.worksheet(tab_name)
            mappings = extract_cash_mappings_from_tab(ws)
            
            if mappings:
                # Use lowercase property code as key
                prop_code = tab_name.lower()
                all_mappings[prop_code] = mappings
                print(f"    [OK] Found {len(mappings)} cash mappings")
            else:
                print(f"    [WARN] No cash mappings found")
            
            # Rate limiting delay
            if i < len(property_tabs):
                time.sleep(delay)
                
        except gspread.WorksheetNotFound:
            print(f"    [WARN] Tab not found: {tab_name}")
        except Exception as e:
            print(f"    [WARN] Error: {e}")
            # Wait longer on error (likely rate limit)
            time.sleep(delay * 2)
    
    return all_mappings


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch cash account mappings from Google Sheets")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(__file__).parent.parent / "12. Dec" / "Input" / "cash_account_mappings.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()
    
    print(f"Connecting to Google Sheet: {SHEET_ID}")
    sh = connect_sheet()
    print(f"Connected: {sh.title}")
    
    print("\nFetching cash account mappings...")
    all_mappings = fetch_all_cash_mappings(sh)
    
    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Write JSON output
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(all_mappings, f, indent=2, sort_keys=True)
    
    print(f"\n[SUCCESS] Wrote {len(all_mappings)} property mappings to: {args.output}")
    
    # Print summary
    print("\nSummary:")
    for prop, mappings in sorted(all_mappings.items()):
        print(f"  {prop}: {len(mappings)} cash descriptions")


if __name__ == "__main__":
    main()
