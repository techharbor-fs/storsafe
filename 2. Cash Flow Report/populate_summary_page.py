"""
Populate Summary Page with Dynamic Cell References

Fills Summary Page hard asset properties with direct cell reference formulas:
- Column C/G: Net Operating Income (from source sheet)
- Column D/H: Net Income (from source sheet)
- Column E/I: Adjusted Cash Flow (from generated report)

Dynamically finds row numbers by searching for text (not hard-coded).
Creates direct cell references (e.g., ='Sheet'!K150), not VLOOKUPs.

Configuration: Edit parameters below before running
"""

import json
import os
import tempfile
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import time

# ============================================================================
# CONFIGURATION PARAMETERS - EDIT THESE
# ============================================================================

# Report details
MONTH = "Sep"           # Month name (e.g., "Aug", "Sep", "Oct")
YEAR = 2025             # Year

# Credentials and spreadsheet (DO NOT EDIT)
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
SPREADSHEET_ID = '1U-1dz3mQoICSSqh-w87eIH2MVdotQKg7JuNTliQqsuA'

# ============================================================================
# DO NOT EDIT BELOW THIS LINE
# ============================================================================

SUMMARY_SHEET_NAME = "Summary page"

# Define both monthly and YTD configurations
REPORT_CONFIGS = {
    'monthly': {
        'output_sheet': f"Cash Flow Report (All) - {MONTH}",
        'source_sheet': f"Cash Flow ({MONTH})",
        'col_noi': 3,  # Column C
        'col_ni': 4,   # Column D
        'col_acf': 5,  # Column E
    },
    'ytd': {
        'output_sheet': f"Cash Flow Report (All) - YTD.{MONTH}",
        'source_sheet': f"Cash Flow (YTD-{MONTH})",
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
# MAIN PROCESSING LOOP - HANDLE BOTH MONTHLY AND YTD
# ============================================================================

# Open Summary Page once (used by both reports)
try:
    summary_sheet = spreadsheet.worksheet(SUMMARY_SHEET_NAME)
    print(f"\n✓ Opened: {SUMMARY_SHEET_NAME}")
except Exception as e:
    print(f"✗ Error opening Summary page: {e}")
    exit(1)

# Get hard asset properties from Summary Page once (same for both reports)
print("\n" + "=" * 80)
print("Finding hard asset properties in Summary Page...")
print("=" * 80)

summary_col_b = summary_sheet.col_values(2)
summary_col_a = summary_sheet.col_values(1)
properties_row = None

for i, val in enumerate(summary_col_b, 1):
    if val and isinstance(val, str) and 'propert' in normalize_text(val):
        properties_row = i
        print(f"✓ Found 'Properties' header at row {i}")
        break

if not properties_row:
    print("✗ ERROR: Could not find 'Properties' section in Summary Page")
    exit(1)

# Process both Monthly and YTD reports
for idx, (report_type, config) in enumerate(REPORT_CONFIGS.items()):
    # Add delay between reports to avoid API rate limits
    if idx > 0:
        print("\n⏱ Waiting 15 seconds to avoid API rate limits...")
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
        print(f"✓ Opened: {SOURCE_SHEET_NAME}")
    except Exception as e:
        print(f"✗ Error opening source sheet: {e}")
        print(f"⚠ Skipping {report_type} report")
        continue
    
    try:
        report_sheet = spreadsheet.worksheet(OUTPUT_SHEET_NAME)
        print(f"✓ Opened: {OUTPUT_SHEET_NAME}")
    except Exception as e:
        print(f"✗ Error opening generated report: {e}")
        print(f"⚠ Skipping {report_type} report")
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
            print(f"✓ Found Net Operating Income at row {i}")
        elif normalized == 'net income':
            ni_row = i
            print(f"✓ Found Net Income at row {i}")
    
    if not noi_row or not ni_row:
        print(f"✗ ERROR: Could not find NOI or NI in source sheet")
        print(f"⚠ Skipping {report_type} report")
        continue
    
    # Find Adjusted Cash Flow row in generated report (Column C)
    report_col_c = report_sheet.col_values(3)
    acf_row = None
    
    for i, val in enumerate(report_col_c, 1):
        normalized = normalize_text(val)
        if 'adjusted cash flow' in normalized:
            acf_row = i
            print(f"✓ Found Adjusted Cash Flow at row {i}")
            break
    
    if not acf_row:
        print(f"✗ ERROR: Could not find 'Adjusted Cash Flow' in report")
        print(f"⚠ Skipping {report_type} report")
        continue
    
    # ========================================================================
    # PHASE 3: GET PROPERTY CODES FROM SOURCE SHEET ROW 5
    # ========================================================================
    
    print("\n" + "-" * 80)
    print(f"Reading property codes from source sheet...")
    print("-" * 80)
    
    source_row_5 = source_sheet.row_values(5)
    property_code_map = {}  # {property_code: column_number}
    
    for col_idx, code in enumerate(source_row_5, 1):
        if code and isinstance(code, str) and code.strip():
            property_code_map[code.strip().lower()] = col_idx
    
    print(f"✓ Found {len(property_code_map)} property codes in source sheet row 5")
    
    # ========================================================================
    # PHASE 4: MATCH PROPERTIES AND BUILD FORMULAS
    # ========================================================================
    
    print("\n" + "-" * 80)
    print(f"Building formulas for {report_type} columns...")
    print("-" * 80)
    
    properties_to_update = []
    
    for row_idx in range(properties_row + 1, len(summary_col_a) + 1):
        if row_idx > len(summary_col_a):
            break
        
        property_code = summary_col_a[row_idx - 1] if row_idx <= len(summary_col_a) else ""
        property_name = summary_col_b[row_idx - 1] if row_idx <= len(summary_col_b) else ""
        
        # Stop if both columns are empty
        if not property_code and not property_name:
            break
        
        # Skip rows where column A is empty
        if not property_code or not isinstance(property_code, str):
            continue
        
        property_code = property_code.strip().lower()
        
        # Check if this property exists in source sheet
        if property_code in property_code_map:
            properties_to_update.append((row_idx, property_code, property_name))
    
    print(f"✓ Found {len(properties_to_update)} properties to update")
    
    # ========================================================================
    # CLEAR OLD FORMULAS IN TARGET COLUMNS FIRST
    # ========================================================================
    
    print("\n" + "-" * 80)
    print(f"Clearing old formulas in {report_type} columns...")
    print("-" * 80)
    
    # Determine the range to clear based on properties found
    if properties_to_update:
        first_row = properties_to_update[0][0]  # First property row
        last_row = properties_to_update[-1][0]  # Last property row
        
        # Clear the three columns for this report type
        clear_ranges = [
            f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_NOI)}{first_row}:{col_number_to_letter(COL_NOI)}{last_row}',
            f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_NI)}{first_row}:{col_number_to_letter(COL_NI)}{last_row}',
            f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_ACF)}{first_row}:{col_number_to_letter(COL_ACF)}{last_row}',
        ]
        
        try:
            for clear_range in clear_ranges:
                service.spreadsheets().values().clear(
                    spreadsheetId=SPREADSHEET_ID,
                    range=clear_range
                ).execute()
            
            print(f"✓ Cleared columns {chr(64+COL_NOI)}, {chr(64+COL_NI)}, {chr(64+COL_ACF)} (rows {first_row}-{last_row})")
            time.sleep(2)  # Small delay after clearing
            
        except Exception as e:
            print(f"⚠ Warning: Could not clear old formulas: {e}")
    
    # ========================================================================
    # BUILD NEW FORMULAS
    # ========================================================================
    
    # Read report property codes ONCE (outside loop) to avoid excessive API calls
    print("\n" + "-" * 80)
    print("Reading property codes from generated report...")
    print("-" * 80)
    report_row_2 = report_sheet.row_values(2)
    print(f"✓ Found {len([c for c in report_row_2 if c])} property codes in report row 2")
    time.sleep(2)  # Small delay after reading
    
    batch_updates = []
    
    for row_num, property_code, property_name in properties_to_update:
        # Get property column from source sheet
        source_col_num = property_code_map[property_code]
        source_col_letter = col_number_to_letter(source_col_num)
        
        # Find same property in generated report (row 2 has property codes)
        # report_row_2 already loaded above - no need to read again
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
        acf_formula = f"='{OUTPUT_SHEET_NAME}'!{report_col_letter}{acf_row}"
        
        # Add to batch updates
        batch_updates.append({
            'range': f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_NOI)}{row_num}',
            'values': [[noi_formula]]
        })
        batch_updates.append({
            'range': f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_NI)}{row_num}',
            'values': [[ni_formula]]
        })
        batch_updates.append({
            'range': f'{SUMMARY_SHEET_NAME}!{col_number_to_letter(COL_ACF)}{row_num}',
            'values': [[acf_formula]]
        })
    
    print(f"✓ Prepared {len(batch_updates)} cell updates")
    
    # ========================================================================
    # PHASE 5: APPLY UPDATES TO SUMMARY PAGE
    # ========================================================================
    
    print("\n" + "-" * 80)
    print(f"Applying {report_type} formulas to Summary Page...")
    print("-" * 80)
    
    if not batch_updates:
        print(f"⚠ No updates to apply for {report_type}")
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
            print(f"✓ Successfully updated {updated_cells} cells for {report_type}")
            
        except Exception as e:
            print(f"✗ Error applying updates: {e}")

# ============================================================================
# COMPLETE
# ============================================================================

print("\n" + "=" * 80)
print("✓ SUMMARY PAGE POPULATION COMPLETE")
print("=" * 80)
print(f"\nProcessed both Monthly (C-E) and YTD (G-I) reports")
