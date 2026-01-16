"""
Populate Summary Page with Dynamic Cell References

Fills Summary Page hard asset properties with direct cell reference formulas:
- Column C/G: Net Operating Income (from source sheet)
- Column D/H: Net Income (from source sheet)
- Column E/I: Adjusted Cash Flow (from generated report)

Dynamically finds row numbers by searching for text (not hard-coded).
Creates direct cell references (e.g., ='Sheet'!K150), not VLOOKUPs.

Configuration: Uses environment variables or command-line arguments
"""

import json
import os
import sys
import argparse
import tempfile
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import time

# ============================================================================
# CONFIGURATION - Environment Variables or Arguments
# ============================================================================

def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val.strip() if isinstance(val, str) and val.strip() else default


def _extract_sheet_id(value: str) -> str:
    """Extract sheet ID from URL or return as-is if already an ID."""
    value = (value or "").strip()
    if not value:
        return value
    marker = "/spreadsheets/d/"
    if marker in value:
        after = value.split(marker, 1)[1]
        return after.split("/", 1)[0]
    return value


# Credentials setup
service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
if service_account_json:
    temp_json_path = Path(tempfile.gettempdir()) / "service_account.json"
    temp_json_path.write_text(json.dumps(json.loads(service_account_json)), encoding="utf-8")
    SERVICE_ACCOUNT_FILE = str(temp_json_path)
else:
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("SERVICE_ACCOUNT_FILE")
    if not env_path:
        raise RuntimeError(
            "Missing Google service account credentials. Set SERVICE_ACCOUNT_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS/SERVICE_ACCOUNT_FILE."
        )
    SERVICE_ACCOUNT_FILE = env_path


def main():
    parser = argparse.ArgumentParser(description="Populate Summary Page with formulas")
    parser.add_argument(
        "--sheet-id",
        default=_env("CF_SPREADSHEET_ID", ""),
        help="Target Google Sheet ID or URL",
    )
    parser.add_argument(
        "--month",
        default=_env("CF_MONTH", "Nov"),
        help="Month name (e.g., Nov, Dec, Jan)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=int(_env("CF_YEAR", "2025")),
        help="Year (e.g., 2025)",
    )
    parser.add_argument(
        "--summary-tab",
        default=_env("CF_SUMMARY_TAB", "Summary page"),
        help="Name of the Summary Page tab",
    )
    args = parser.parse_args()

    SPREADSHEET_ID = _extract_sheet_id(args.sheet_id)
    if not SPREADSHEET_ID:
        print("[ERROR] No spreadsheet ID provided. Use --sheet-id or set CF_SPREADSHEET_ID")
        sys.exit(1)

    MONTH = args.month
    YEAR = args.year
    MONTH_UPPER = MONTH.upper()[:3] if len(MONTH) >= 3 else MONTH.upper()
    SUMMARY_SHEET_NAME = args.summary_tab

    # Define both monthly and YTD configurations
    # Updated to use new naming convention: CASH FLOW (ALL) - {MONTH} and HA-CF-{MONTH}
    REPORT_CONFIGS = {
        'monthly': {
            'output_sheet': f"CASH FLOW (ALL) - {MONTH_UPPER}",
            'source_sheet': f"HA-CF-{MONTH_UPPER}",
            'col_noi': 3,  # Column C
            'col_ni': 4,   # Column D
            'col_acf': 5,  # Column E
        },
        'ytd': {
            'output_sheet': f"CASH FLOW (ALL) - YTD",
            'source_sheet': f"HA-CF-YTD",
            'col_noi': 7,  # Column G
            'col_ni': 8,   # Column H
            'col_acf': 9,  # Column I
        }
    }

    # Google Sheets setup
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    service = build('sheets', 'v4', credentials=creds)

    # Open spreadsheet
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)

    print("=" * 80)
    print(f"SUMMARY PAGE POPULATION - MONTHLY + YTD")
    print("=" * 80)
    print(f"\nTarget: {SUMMARY_SHEET_NAME}")
    print(f"Processing both Monthly and YTD reports for {MONTH} {YEAR}")

    # ============================================================================
    # HELPER FUNCTIONS
    # ============================================================================

    def normalize_text(text):
        """Normalize text for comparison (strip whitespace, lowercase)"""
        if not text or not isinstance(text, str):
            return ""
        return ' '.join(text.strip().split()).lower()

    def col_number_to_letter(col_num):
        """Convert column number to letter (1=A, 2=B, ..., 27=AA, etc.)"""
        result = ""
        while col_num > 0:
            col_num -= 1
            result = chr(65 + (col_num % 26)) + result
            col_num //= 26
        return result

    # ============================================================================
    # MAIN PROCESSING
    # ============================================================================

    # Open Summary Page once (used by both reports)
    try:
        summary_sheet = spreadsheet.worksheet(SUMMARY_SHEET_NAME)
        print(f"\n[OK] Opened: {SUMMARY_SHEET_NAME}")
    except Exception as e:
        print(f"[ERROR] Error opening Summary page: {e}")
        print("[WARN] Summary page not found - skipping population")
        return

    # Get hard asset properties from Summary Page once (same for both reports)
    print("\n" + "=" * 80)
    print("Finding all sections in Summary Page...")
    print("=" * 80)

    summary_col_b = summary_sheet.col_values(2)
    summary_col_a = summary_sheet.col_values(1)
    
    # Find the first section header (Corporate, Laundromat, or Properties)
    # to determine where data starts
    first_data_row = None
    section_headers = ['corporate', 'laundromat', 'propert']
    
    for i, val in enumerate(summary_col_b, 1):
        if val and isinstance(val, str):
            normalized = normalize_text(val)
            for header in section_headers:
                if header in normalized:
                    first_data_row = i
                    print(f"[OK] Found first section '{val}' at row {i}")
                    break
            if first_data_row:
                break
    
    if not first_data_row:
        # Fallback: start from row 4 (after typical header rows)
        first_data_row = 4
        print(f"[WARN] Could not find section headers, starting from row {first_data_row}")

    # Process both Monthly and YTD reports
    for idx, (report_type, config) in enumerate(REPORT_CONFIGS.items()):
        # Add delay between reports to avoid API rate limits
        if idx > 0:
            print("\n   Waiting 15 seconds to avoid API rate limits...")
            time.sleep(15)
        
        print("\n" + "=" * 80)
        print(f"PROCESSING {report_type.upper()} REPORT")
        print("=" * 80)
        
        OUTPUT_SHEET_NAME = config['output_sheet']
        SOURCE_SHEET_NAME = config['source_sheet']
        COL_NOI = config['col_noi']
        COL_NI = config['col_ni']
        COL_ACF = config['col_acf']
        
        print(f"\nSource Sheet: {SOURCE_SHEET_NAME}")
        print(f"Generated Report: {OUTPUT_SHEET_NAME}")
        print(f"Columns: NOI={chr(64+COL_NOI)}, NI={chr(64+COL_NI)}, ACF={chr(64+COL_ACF)}")
        
        # ========================================================================
        # PHASE 1: OPEN SHEETS AND VALIDATE
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Opening {report_type} sheets...")
        print("-" * 80)
        
        try:
            source_sheet = spreadsheet.worksheet(SOURCE_SHEET_NAME)
            print(f"[OK] Opened: {SOURCE_SHEET_NAME}")
        except Exception as e:
            print(f"[ERROR] Error opening source sheet: {e}")
            print(f"[WARN] Skipping {report_type} report")
            continue
        
        try:
            report_sheet = spreadsheet.worksheet(OUTPUT_SHEET_NAME)
            print(f"[OK] Opened: {OUTPUT_SHEET_NAME}")
        except Exception as e:
            print(f"[ERROR] Error opening generated report: {e}")
            print(f"[WARN] Skipping {report_type} report")
            continue
        
        # ========================================================================
        # PHASE 2: FIND KEY ROWS DYNAMICALLY
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Finding key rows in {report_type} sheets...")
        print("-" * 80)
        
        # Find NOI and NI rows in source sheet (Column B)
        source_col_b = source_sheet.col_values(2)
        noi_row = None
        ni_row = None
        
        for i, val in enumerate(source_col_b, 1):
            normalized = normalize_text(val)
            if 'net operating income' in normalized:
                noi_row = i
                print(f"[OK] Found Net Operating Income at row {i}")
            elif normalized == 'net income':
                ni_row = i
                print(f"[OK] Found Net Income at row {i}")
        
        if not noi_row or not ni_row:
            print(f"[ERROR] Could not find NOI or NI in source sheet")
            print(f"[WARN] Skipping {report_type} report")
            continue
        
        # Find ACF range: Financing Activities section up to (but not including) Equipment Financing
        # ACF = SUM of Financing accounts before Equipment Financing (2135-0020)
        report_col_a = report_sheet.col_values(1)  # GL codes in Column A
        report_col_b = report_sheet.col_values(2)  # Section headers in Column B
        
        financing_start_row = None
        equipment_financing_row = None
        
        # Find "III. Financing Activities" section header in Column B
        for i, val in enumerate(report_col_b, 1):
            normalized = normalize_text(val)
            if 'iii' in normalized and 'financing' in normalized:
                financing_start_row = i
                print(f"[OK] Found 'III. Financing Activities' header at row {i}")
                break
        
        # Find Equipment Financing by GL code 2135-0020 in Column A
        for i, val in enumerate(report_col_a, 1):
            if val and isinstance(val, str) and val.strip() == '2135-0020':
                equipment_financing_row = i
                print(f"[OK] Found Equipment Financing (2135-0020) at row {i}")
                break
        
        if not financing_start_row:
            print(f"[ERROR] Could not find 'III. Financing Activities' section in report")
            print(f"[WARN] Skipping {report_type} report")
            continue
        
        if not equipment_financing_row:
            print(f"[ERROR] Could not find Equipment Financing (2135-0020) in report")
            print(f"[WARN] Skipping {report_type} report")
            continue
        
        # ACF range: first Financing account row to row before Equipment Financing
        acf_start_row = financing_start_row + 1  # First account after header
        acf_end_row = equipment_financing_row - 1  # Row before Equipment Financing
        
        print(f"[OK] ACF will sum rows {acf_start_row} to {acf_end_row} (Financing accounts before Equipment Financing)")
        
        # ========================================================================
        # PHASE 3: GET PROPERTY CODES FROM SOURCE SHEET
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Reading property codes from source sheet...")
        print("-" * 80)
        
        # DYNAMIC: Find property codes row (look for 'Total')
        source_property_row = None
        for row_num in range(1, 20):
            row_data = source_sheet.row_values(row_num)
            if row_data and 'Total' in row_data and len([v for v in row_data if v and v.strip()]) > 5:
                source_property_row = row_data
                print(f"[OK] Found property codes in source row {row_num}")
                break
        
        if not source_property_row:
            source_property_row = source_sheet.row_values(5)
            print(f"[WARN] Using default row 5 for property codes")
        
        property_code_map = {}  # {property_code: column_number}
        
        for col_idx, code in enumerate(source_property_row, 1):
            if code and isinstance(code, str) and code.strip():
                property_code_map[code.strip().lower()] = col_idx
        
        print(f"[OK] Found {len(property_code_map)} property codes in source sheet")
        
        # ========================================================================
        # PHASE 4: FIND ALL PROPERTY ROWS AND MATCH TO SOURCE
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Finding all property rows for {report_type} columns...")
        print("-" * 80)
        
        # Collect ALL property rows (rows with property code in column A)
        all_property_rows = []  # All rows with a property code (for clearing)
        properties_to_update = []  # Only rows that exist in source (for formulas)
        
        consecutive_empty = 0
        for row_idx in range(first_data_row + 1, len(summary_col_a) + 1):
            if row_idx > len(summary_col_a):
                break
            
            property_code = summary_col_a[row_idx - 1] if row_idx <= len(summary_col_a) else ""
            property_name = summary_col_b[row_idx - 1] if row_idx <= len(summary_col_b) else ""
            
            # Track consecutive empty rows - stop after 5 in a row (end of data)
            if not property_code and not property_name:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break
                continue
            else:
                consecutive_empty = 0
            
            # Skip section headers (Corporate, Laundromat, Properties, TOTAL, etc.)
            # These have names in column B but are not individual properties
            name_lower = (property_name or "").strip().lower() if isinstance(property_name, str) else ""
            section_keywords = ['corporate', 'laundromat', 'properties', 'total', 'dre jv']
            is_section_header = any(kw in name_lower for kw in section_keywords)
            
            if is_section_header:
                continue
            
            # If column B has a name but column A is empty, still include for clearing
            # (This catches rows like EP Legacy, Elmdale Holdings, SSSM, Happy Life)
            if property_name and isinstance(property_name, str) and property_name.strip():
                property_code_clean = property_code.strip().lower() if property_code and isinstance(property_code, str) else ""
                
                # Add to all_property_rows (for clearing)
                all_property_rows.append((row_idx, property_code_clean, property_name))
                
                # Check if this property exists in source sheet (for formulas)
                # Only add to properties_to_update if we have a valid code that exists in source
                if property_code_clean and property_code_clean in property_code_map:
                    properties_to_update.append((row_idx, property_code_clean, property_name))
        
        print(f"[OK] Found {len(all_property_rows)} total property rows")
        print(f"[OK] Found {len(properties_to_update)} properties with source data")
        
        # ========================================================================
        # CLEAR ALL PROPERTY ROWS (removes #REF! from properties not in source)
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Clearing ALL property cells in {report_type} columns...")
        print("-" * 80)
        
        # Clear ALL property rows (not just ones we're updating)
        # This removes #REF! errors from properties that don't exist in current source
        if all_property_rows:
            clear_cells = []
            for row_num, property_code, property_name in all_property_rows:
                clear_cells.append(f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_NOI)}{row_num}")
                clear_cells.append(f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_NI)}{row_num}")
                clear_cells.append(f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_ACF)}{row_num}")
            
            try:
                # Use batchClear for multiple non-contiguous cells
                service.spreadsheets().values().batchClear(
                    spreadsheetId=SPREADSHEET_ID,
                    body={'ranges': clear_cells}
                ).execute()
                
                print(f"[OK] Cleared {len(clear_cells)} cells ({len(all_property_rows)} property rows x 3 columns)")
                time.sleep(2)  # Small delay after clearing
                
            except Exception as e:
                print(f"[WARN] Could not clear old formulas: {e}")
        
        # ========================================================================
        # BUILD NEW FORMULAS
        # ========================================================================
        
        # Read report property codes ONCE (outside loop) to avoid excessive API calls
        print("\n" + "-" * 80)
        print("Reading property codes from generated report...")
        print("-" * 80)
        report_row_2 = report_sheet.row_values(2)
        print(f"[OK] Found {len([c for c in report_row_2 if c])} property codes in report row 2")
        time.sleep(2)  # Small delay after reading
        
        batch_updates = []
        
        for row_num, property_code, property_name in properties_to_update:
            # Get property column from source sheet
            source_col_num = property_code_map[property_code]
            source_col_letter = col_number_to_letter(source_col_num)
            
            # Find same property in generated report (row 2 has property codes)
            report_col_num = None
            
            for col_idx, code in enumerate(report_row_2, 1):
                if code and isinstance(code, str) and code.strip().lower() == property_code:
                    report_col_num = col_idx
                    break
            
            if not report_col_num:
                continue
            
            report_col_letter = col_number_to_letter(report_col_num)
            
            # Build formulas
            noi_formula = f"='{SOURCE_SHEET_NAME}'!{source_col_letter}{noi_row}"
            ni_formula = f"='{SOURCE_SHEET_NAME}'!{source_col_letter}{ni_row}"
            # ACF = SUM of Financing accounts before Equipment Financing
            acf_formula = f"=SUM('{OUTPUT_SHEET_NAME}'!{report_col_letter}{acf_start_row}:{report_col_letter}{acf_end_row})"
            
            # Add to batch updates
            batch_updates.append({
                'range': f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_NOI)}{row_num}",
                'values': [[noi_formula]]
            })
            batch_updates.append({
                'range': f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_NI)}{row_num}",
                'values': [[ni_formula]]
            })
            batch_updates.append({
                'range': f"'{SUMMARY_SHEET_NAME}'!{col_number_to_letter(COL_ACF)}{row_num}",
                'values': [[acf_formula]]
            })
        
        print(f"[OK] Prepared {len(batch_updates)} cell updates")
        
        # ========================================================================
        # PHASE 5: APPLY UPDATES TO SUMMARY PAGE
        # ========================================================================
        
        print("\n" + "-" * 80)
        print(f"Applying {report_type} formulas to Summary Page...")
        print("-" * 80)
        
        if not batch_updates:
            print(f"[WARN] No updates to apply for {report_type}")
        else:
            try:
                body = {
                    'valueInputOption': 'USER_ENTERED',
                    'data': batch_updates
                }
                
                result = service.spreadsheets().values().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body=body
                ).execute()
                
                updated_cells = result.get('totalUpdatedCells', 0)
                print(f"[OK] Successfully updated {updated_cells} cells for {report_type}")
                
            except Exception as e:
                print(f"[ERROR] Error applying updates: {e}")

    # ============================================================================
    # COMPLETE
    # ============================================================================

    print("\n" + "=" * 80)
    print("[OK] SUMMARY PAGE POPULATION COMPLETE")
    print("=" * 80)
    print(f"\nProcessed both Monthly (C-E) and YTD (G-I) reports")


if __name__ == "__main__":
    main()
