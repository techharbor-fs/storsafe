"""
Production Cash Flow Report Generator for StorSafe

Generates monthly and YTD Cash Flow Reports with:
- Dynamic GL categorization
- Cash Account Realignment
- Complete formatting (borders, colors, fonts, alignment)
- Row 1 status lookups from previous month

Configuration: Edit parameters below before running
"""

import json
import os
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import time

# ============================================================================
# CONFIGURATION PARAMETERS - EDIT THESE
# ============================================================================

def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val.strip() if isinstance(val, str) and val.strip() else default


# Report details
# (Can be overridden by env vars when running from the merged workflow.)
MONTH = _env("CF_MONTH", "Sep")            # Month name (e.g., "Aug", "Sep", "Oct")
YEAR = int(_env("CF_YEAR", "2025"))        # Year
REPORT_TYPE = _env("CF_REPORT_TYPE", "ytd") # "monthly" or "ytd"

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
SPREADSHEET_ID = _env("CF_SPREADSHEET_ID", "1U-1dz3mQoICSSqh-w87eIH2MVdotQKg7JuNTliQqsuA")

# Sheet names will be auto-generated based on above:
# Monthly: "Cash Flow Report (All) - Aug"
# YTD:     "Cash Flow Report (All) - YTD.Aug"  (Note: period before month)
# Row 1 status data comes from: "Property Status Tracker" sheet

# ============================================================================
# DO NOT EDIT BELOW THIS LINE
# ============================================================================

# Auto-generate sheet names based on configuration
# Uses HA-* tab naming convention (same as v2 workflow)
MONTH_UPPER = MONTH.upper()[:3] if len(MONTH) >= 3 else MONTH.upper()

if REPORT_TYPE == "ytd":
    OUTPUT_SHEET_NAME = f"Cash Flow Report (All) - YTD.{MONTH}"  # Format: YTD.Aug (matches July)
    SOURCE_SHEET_NAME = f"HA-CF-YTD"  # v2 tab name
    BALANCE_SHEET_NAME = f"HA-BS-{MONTH_UPPER}"  # v2 tab name
    REPORT_TITLE = f"Cash Flow Report ({MONTH} {YEAR} YTD)"
else:  # monthly
    OUTPUT_SHEET_NAME = f"Cash Flow Report (All) - {MONTH}"
    SOURCE_SHEET_NAME = f"HA-CF-{MONTH_UPPER}"  # v2 tab name
    BALANCE_SHEET_NAME = f"HA-BS-{MONTH_UPPER}"  # v2 tab name
    REPORT_TITLE = f"Cash Flow Report ({MONTH} {YEAR})"

# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
service = build('sheets', 'v4', credentials=creds)

# Open spreadsheet
spreadsheet = gc.open_by_key(SPREADSHEET_ID)

print("=" * 80)
print(f"CASH FLOW REPORT GENERATION - {REPORT_TYPE.upper()}")
print("=" * 80)
print(f"\nOutput: {OUTPUT_SHEET_NAME}")
print(f"Source: {SOURCE_SHEET_NAME}")
print(f"Balance Sheet: {BALANCE_SHEET_NAME}")
print(f"Row 1 Status Source: Property Status Tracker")

# ============================================================================
# GL CODE CATEGORIZATION LOGIC
# ============================================================================

def categorize_gl_code(gl_code):
    """
    Categorize GL code based on first 2-4 digits
    
    Rules:
    1. Restricted Cash: 1200-xxxx
    2. Investing: 1410-xxxx (Land), 1500-xxxx, 1600-xxxx, 1770-xxxx (Personal Property/Goodwill), 
                  1800-xxxx (Merchandise Supplies), 1900-xxxx (Investments), 1910-xxxx (Disputed/Other)
    3. Financing: 21xx-xxxx, 2290-xxxx, 3xxx-xxxx
    4. Operating: Everything else (including 9090)
    """
    if not gl_code:
        return None
    
    prefix = gl_code.split('-')[0]
    first_two = prefix[:2] if len(prefix) >= 2 else None
    first_four = prefix[:4] if len(prefix) >= 4 else None
    
    # Restricted Cash
    if first_four == '1200':
        return 'Restricted'
    
    # Investing Activities
    if first_four in ['1410', '1500', '1600', '1770', '1800', '1900', '1910']:
        return 'Investing'
    
    # Financing Activities
    if first_two == '21':  # Notes Payable
        return 'Financing'
    
    if first_four == '2290':  # Funds for Transfer
        return 'Financing'
    
    if prefix[0] == '3':  # Equity accounts
        return 'Financing'
    
    # Operating Activities (everything else)
    return 'Operating'

# ============================================================================
# PHASE 1: CREATE BLANK SHEET
# ============================================================================

print("\n PHASE 1: Create Blank Sheet")
print("-" * 80)

# Delete existing sheet if it exists
try:
    existing_test = spreadsheet.worksheet(OUTPUT_SHEET_NAME)
    print(f"     Sheet '{OUTPUT_SHEET_NAME}' already exists")
    print("     Deleting existing sheet...")
    spreadsheet.del_worksheet(existing_test)
    print("    Deleted old sheet")
    time.sleep(2)
except gspread.exceptions.WorksheetNotFound:
    print(f"     No existing sheet found")

# Create brand new blank sheet with sufficient rows/columns
print(f"\n Creating brand new blank sheet: '{OUTPUT_SHEET_NAME}'...")
test_sheet = spreadsheet.add_worksheet(title=OUTPUT_SHEET_NAME, rows=200, cols=55)
test_sheet_id = test_sheet.id
print(f"    Created blank sheet (ID: {test_sheet_id})")

# Set sheet tab color to blue
# Set sheet tab color to pure blue (same as July reports)
print("    Setting sheet tab color to pure blue...")
service.spreadsheets().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body={
        'requests': [{
            'updateSheetProperties': {
                'properties': {
                    'sheetId': test_sheet_id,
                    'tabColor': {
                        'red': 0.0,
                        'green': 0.0,
                        'blue': 1.0
                    }
                },
                'fields': 'tabColor'
            }
        }]
    }
).execute()
print("    Sheet tab color set to pure blue")

# ============================================================================
# PHASE 2: DISCOVER STRUCTURE DYNAMICALLY
# ============================================================================

print("\n\n PHASE 2: Dynamic Structure Discovery")
print("-" * 80)

# Read SOURCE sheet adjustments section
print("\n Step 2.1: Reading SOURCE sheet adjustments...")
source_sheet = spreadsheet.worksheet(SOURCE_SHEET_NAME)

# First, find the NET INCOME row dynamically (YTD has different structure)
print("    Finding NET INCOME row...")
search_range = source_sheet.get('A140:B250')  # Wide search range
net_income_search_row = None
for idx, row in enumerate(search_range, start=140):
    if row and len(row) >= 1 and '9090-0000' in str(row[0]):
        net_income_search_row = idx
        print(f"    Found NET INCOME at row {idx}")
        break

if not net_income_search_row:
    raise ValueError("Could not find NET INCOME (9090-0000) in SOURCE sheet")

# Read adjustments section starting from NET INCOME row
# Instead of fixed 60 rows, read until we find blank rows (end of section)
adjustments_start = net_income_search_row
print("    Reading all GL accounts until section end...")

# Read larger range initially to ensure we capture all accounts
initial_read_size = 150  # Read up to 150 rows to be safe
adjustments_range_raw = source_sheet.get(f'A{adjustments_start}:B{adjustments_start + initial_read_size}')

# Find actual end of data (two consecutive rows with BOTH columns blank)
adjustments_range = []
blank_count = 0
for row_data in adjustments_range_raw:
    gl_code = row_data[0].strip() if len(row_data) > 0 and row_data[0] else None
    description = row_data[1].strip() if len(row_data) > 1 and row_data[1] else None
    
    # Row is blank only if BOTH GL code AND description are empty
    if not gl_code and not description:
        blank_count += 1
        if blank_count >= 2:  # Two consecutive blank rows = end of section
            break
    else:
        blank_count = 0  # Reset counter when we find data
        adjustments_range.append(row_data)

adjustments_end = adjustments_start + len(adjustments_range)
print(f"    Fetched {len(adjustments_range)} GL accounts (rows {adjustments_start}-{adjustments_end})")

# Process adjustments and categorize
net_income_row = None
gl_accounts = {
    'Operating': [],
    'Investing': [],
    'Financing': [],
    'Restricted': []
}

print("\n Step 2.2: Categorizing GL codes...")

for idx, row_data in enumerate(adjustments_range):
    source_row = adjustments_start + idx  # Use dynamic starting row
    gl_code = row_data[0].strip() if len(row_data) > 0 and row_data[0] else None
    description = row_data[1].strip() if len(row_data) > 1 and row_data[1] else None
    
    if not gl_code:
        continue
    
    # Skip header rows
    if 'ADJUSTMENT' in str(gl_code).upper():
        continue
    
    # Skip income/expense accounts (only include balance sheet accounts)
    # Include: Assets (1xxx), Liabilities (2xxx), Equity (3xxx), Net Income (9090-0000)
    # Exclude: Income/Expense (4xxx, 5xxx, 6xxx, 7xxx, 8xxx, 9xxx except 9090)
    first_digit = gl_code[0] if gl_code else ''
    if first_digit in ['4', '5', '6', '7', '8']:
        print(f"     SKIP (Income/Expense): {gl_code} | {description}")
        continue
    if first_digit == '9' and gl_code != '9090-0000':
        print(f"     SKIP (Income/Expense): {gl_code} | {description}")
        continue
    
    # Handle NET INCOME specially
    if gl_code == '9090-0000':
        net_income_row = source_row
        gl_accounts['Operating'].insert(0, (gl_code, description, source_row))
        print(f"    Found NET INCOME: {gl_code} at SOURCE row {source_row}")
        continue
    
    # Categorize GL code
    category = categorize_gl_code(gl_code)
    
    if category:
        gl_accounts[category].append((gl_code, description, source_row))
        print(f"   {category:12s}: {gl_code:15s} | {description:40s} -> Row {source_row}")

print(f"\n    Categorized GL accounts:")
print(f"      Operating:  {len(gl_accounts['Operating'])} accounts")
print(f"      Investing:  {len(gl_accounts['Investing'])} accounts")
print(f"      Financing:  {len(gl_accounts['Financing'])} accounts")
print(f"      Restricted: {len(gl_accounts['Restricted'])} accounts")

# Initialize excluded properties list (will be populated after reading Property Status Tracker)
excluded_properties = []

# Read property mapping from SOURCE sheet
print("\n Step 2.3: Reading property mapping...")
# CRITICAL: Row 5 contains property codes (e.g., '1288rick', 'cpwest', 'ephss')
# Row 1 is typically blank or contains only the report title
source_row_5 = source_sheet.row_values(5)  # Row 5 has property codes

property_to_source_col = {}
for idx, value in enumerate(source_row_5):
    if idx < 2:  # Skip columns A and B
        continue
    if value and value.strip():
        col_letter = gspread.utils.rowcol_to_a1(1, idx + 1).replace('1', '')
        property_to_source_col[value.strip()] = col_letter

print(f"    Mapped {len(property_to_source_col)} properties from SOURCE sheet")

# Read baseline for property order - ALWAYS use SOURCE sheet row 5
print("\n Step 2.4: Reading baseline property order...")
# SOURCE sheet row 5 has all property codes in the correct order (including Total)
baseline_row_5 = source_row_5

report_properties = []
for idx, value in enumerate(baseline_row_5):
    if idx < 2:  # Skip columns A-B (GL code and description in SOURCE)
        continue
    if value and value.strip():
        prop_code = value.strip()
        # Skip if property code is in excluded list
        if prop_code in excluded_properties:
            print(f"     Skipping '{prop_code}' - status is skip/sold")
            continue
        report_properties.append(prop_code)

print(f"    Found {len(report_properties)} properties in correct order")

# Calculate column assignments
property_to_report_col = {}
first_property_col = 'F'
first_col_index = gspread.utils.a1_to_rowcol(f'{first_property_col}1')[1]

for idx, prop in enumerate(report_properties):
    col_index = first_col_index + idx
    col_letter = gspread.utils.rowcol_to_a1(1, col_index).replace('1', '')
    property_to_report_col[prop] = col_letter

# Find last column (Total column or last property)
total_column = property_to_report_col.get('Total', property_to_report_col.get('total'))
if not total_column:
    # No Total column found, use last property column
    total_column = gspread.utils.rowcol_to_a1(1, first_col_index + len(report_properties) - 1).replace('1', '')

last_property_col = gspread.utils.rowcol_to_a1(1, first_col_index + len(report_properties) - 2).replace('1', '')

print(f"    Column assignments: F through {total_column}")

# Read Cash Account Realignment accounts from Balance Sheet
print("\n Step 2.5: Reading Cash Account Realignment from Balance Sheet...")
balance_sheet = spreadsheet.worksheet(BALANCE_SHEET_NAME)

# Get all cash accounts from Balance Sheet (rows 80-95 typically)
bs_cash_accounts = balance_sheet.get('A80:B95')

realignment_accounts = []
restricted_gl_codes = {gl[0] for gl in gl_accounts['Restricted']}

for idx, row_data in enumerate(bs_cash_accounts):
    bs_row = 80 + idx
    gl_code = row_data[0].strip() if len(row_data) > 0 and row_data[0] else None
    description = row_data[1].strip() if len(row_data) > 1 and row_data[1] else None
    
    if not gl_code or not description:
        continue
    
    # Skip section headers (master accounts ending in -0000)
    if gl_code.endswith('-0000'):
        print(f"     SKIP (Header): {gl_code} | {description}")
        continue
    
    # Only include 1200-xxxx accounts that are NOT in Restricted Cash section
    if gl_code.startswith('1200-') and gl_code not in restricted_gl_codes:
        realignment_accounts.append((gl_code, description, bs_row))
        print(f"   Realignment: {gl_code:15s} | {description:40s} -> BS Row {bs_row}")

print(f"    Found {len(realignment_accounts)} realignment accounts")

# Read Row 1 status data from Property Status Tracker sheet
print("\n Step 2.6: Reading Row 1 status data from Property Status Tracker...")
property_status_map = {}  # Property Code → Status Label mapping
# excluded_properties list already initialized earlier (before Step 2.3)
try:
    status_tracker_sheet = spreadsheet.worksheet('Property Status Tracker')
    # Get columns A (Property Code) and B (Status Label), skip header row
    status_data = status_tracker_sheet.get('A2:B100')
    
    if status_data:
        for row in status_data:
            if len(row) >= 2:
                property_code = row[0].strip() if row[0] else None
                status_label = row[1].strip() if row[1] else None
                if property_code:
                    property_status_map[property_code] = status_label if status_label else ""
                    # Exclude properties with 'skip' or 'sold' status
                    if status_label and status_label.lower() in ['skip', 'sold']:
                        excluded_properties.append(property_code)
        
        print(f"    Retrieved status data from 'Property Status Tracker'")
        print(f"     Found {len(property_status_map)} property status mappings")
        if excluded_properties:
            print(f"     Excluding {len(excluded_properties)} properties with 'skip' or 'sold' status: {', '.join(excluded_properties)}")
    else:
        print(f"     No status data found in tracker")
except gspread.exceptions.WorksheetNotFound:
    print(f"     'Property Status Tracker' sheet not found")
    print(f"     Skipping Row 1 status data")

# ============================================================================
# PHASE 3: BUILD STRUCTURE DATA (Headers, Labels, Properties)
# ============================================================================

print("\n\n  PHASE 3: Build Structure Data")
print("-" * 80)

structure_updates = []
formulas_to_update = []  # Move this declaration up here

def add_structure(row, col_letter, value):
    """Add text value to structure"""
    cell_address = f"{col_letter}{row}"
    structure_updates.append({
        'range': f"{OUTPUT_SHEET_NAME}!{cell_address}",
        'values': [[value]]
    })

def add_formula(row, col_letter, formula):
    """Add formula to formulas list"""
    cell_address = f"{col_letter}{row}"
    formulas_to_update.append({
        'range': f"{OUTPUT_SHEET_NAME}!{cell_address}",
        'values': [[formula]]
    })

# Row 1: Property status data (lookup from Property Status Tracker)
# Use VLOOKUP to find status based on property code in Row 2
if property_status_map:
    for idx, prop in enumerate(report_properties):
        col_index = first_col_index + idx
        col_letter = gspread.utils.rowcol_to_a1(1, col_index).replace('1', '')
        
        # Create VLOOKUP formula that:
        # 1. Looks at current report's property code in Row 2 (this column)
        # 2. Finds matching property code in Property Status Tracker (Column A)
        # 3. Returns corresponding status from Column B
        # Formula: =IFERROR(VLOOKUP(F2,'Property Status Tracker'!$A:$B,2,FALSE),"")
        formula = f"=IFERROR(VLOOKUP({col_letter}2,'Property Status Tracker'!$A:$B,2,FALSE),\"\")"
        add_formula(1, col_letter, formula)
    
    print(f"    Added Row 1 status formulas for {len(report_properties)} properties")

# Row 2: Title and property codes
add_structure(2, 'B', REPORT_TITLE)
for idx, prop in enumerate(report_properties):
    col_index = first_col_index + idx
    col_letter = gspread.utils.rowcol_to_a1(1, col_index).replace('1', '')
    add_structure(2, col_letter, prop)

# Build Operating Activities section
current_row = 3
add_structure(current_row, 'B', 'I. Operating Activities')
current_row += 1

operating_start_row = current_row
for gl_code, description, source_row in gl_accounts['Operating']:
    add_structure(current_row, 'A', gl_code)
    add_structure(current_row, 'C', description)
    current_row += 1

operating_subtotal_row = current_row
add_structure(operating_subtotal_row, 'B', 'Net Cash Inflow / (Outflow) from Operating Activities')
current_row += 1

acf_row = current_row
add_structure(acf_row, 'C', 'Adjusted Cash Flow')
current_row += 2

# Build Investing Activities section
investing_section_row = current_row
add_structure(investing_section_row, 'B', 'II. Investing Activities')
current_row += 1

investing_start_row = current_row
for gl_code, description, source_row in gl_accounts['Investing']:
    add_structure(current_row, 'A', gl_code)
    add_structure(current_row, 'C', description)
    current_row += 1

investing_subtotal_row = current_row
add_structure(investing_subtotal_row, 'B', 'Net Cash Inflow / (Outflow) from Investing Activities')
current_row += 2

# Build Financing Activities section
financing_section_row = current_row
add_structure(financing_section_row, 'B', 'III. Financing Activities')
current_row += 1

financing_start_row = current_row
for gl_code, description, source_row in gl_accounts['Financing']:
    add_structure(current_row, 'A', gl_code)
    add_structure(current_row, 'C', description)
    current_row += 1

financing_subtotal_row = current_row
add_structure(financing_subtotal_row, 'B', 'Net Cash Inflow / (Outflow) from Financing Activities')
current_row += 2

# Build Restricted Cash section
restricted_section_row = current_row
add_structure(restricted_section_row, 'B', 'Total Restricted Cash')
current_row += 1

restricted_start_row = current_row
for gl_code, description, source_row in gl_accounts['Restricted']:
    add_structure(current_row, 'A', gl_code)
    add_structure(current_row, 'C', description)
    current_row += 1

restricted_subtotal_row = current_row
add_structure(restricted_subtotal_row, 'B', 'Net Cash Inflow / (Outflow) from Restricted Cash')
current_row += 2

# Summary section
summary_section_row = current_row
add_structure(summary_section_row, 'B', 'Summary')
current_row += 1

summary_operating_row = current_row
add_structure(summary_operating_row, 'C', 'Cash Generated/(Used) by Operating Activities')
current_row += 1

summary_investing_row = current_row
add_structure(summary_investing_row, 'C', 'Cash Generated/(Used) by Investing Activities')
current_row += 1

summary_financing_row = current_row
add_structure(summary_financing_row, 'C', 'Cash Generated/(Used) by Financing Activities')
current_row += 1

summary_net_change_row = current_row
add_structure(summary_net_change_row, 'C', 'Net Change in Cash')
current_row += 1

summary_restricted_row = current_row
add_structure(summary_restricted_row, 'C', 'Change in Restricted Cash')
current_row += 1

summary_total_row = current_row
add_structure(summary_total_row, 'C', 'Net Change')
current_row += 2

# Reconciliation section
recon_beginning_row = current_row
add_structure(recon_beginning_row, 'C', 'Beginning Balance')
current_row += 1

recon_net_cash_row = current_row
add_structure(recon_net_cash_row, 'C', 'Net Cash - See Above')
current_row += 1

recon_ending_row = current_row
add_structure(recon_ending_row, 'C', 'Ending Balance (per Books)')
current_row += 1

recon_bank_row = current_row
add_structure(recon_bank_row, 'C', 'Cash in Bank Balance (As per Balance Sheet)')
current_row += 1

recon_difference_row = current_row
add_structure(recon_difference_row, 'C', 'Difference')
current_row += 2

# Cash Account Realignment section
realignment_section_row = current_row
add_structure(realignment_section_row, 'B', 'Cash Account Realignment')
current_row += 1

realignment_start_row = current_row
for gl_code, description, bs_row in realignment_accounts:
    add_structure(current_row, 'A', gl_code)
    add_structure(current_row, 'C', description)
    current_row += 1

realignment_end_row = current_row - 1

print(f"    Built {len(structure_updates)} structure cells")
print(f"     Realignment section: Rows {realignment_start_row}-{realignment_end_row}")

# Apply structure in one batch
print("\n Applying structure to sheet...")

body = {
    'valueInputOption': 'RAW',
    'data': structure_updates
}

service.spreadsheets().values().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body=body
).execute()

print(f"    Applied all {len(structure_updates)} structure cells in one batch")
print("    Structure complete!")

# ============================================================================
# PHASE 4: BUILD AND APPLY FORMULAS
# ============================================================================

print("\n\n PHASE 4: Build and Apply Formulas")
print("-" * 80)

# formulas_to_update already declared in Phase 3 (removed duplicate)
# add_formula function already declared in Phase 3 (removed duplicate)

# Operating Activities formulas
print("\n Building Operating Activities formulas...")
for idx, (gl_code, description, source_row) in enumerate(gl_accounts['Operating']):
    report_row = operating_start_row + idx
    
    for prop in report_properties:
        if prop == 'Total':
            formula = f"=SUM({first_property_col}{report_row}:{last_property_col}{report_row})"
            add_formula(report_row, total_column, formula)
        else:
            source_col = property_to_source_col.get(prop)
            if source_col:
                formula = f"='{SOURCE_SHEET_NAME}'!{source_col}{source_row}"
                report_col = property_to_report_col[prop]
                add_formula(report_row, report_col, formula)

# Operating Subtotal
for prop in report_properties:
    report_col = property_to_report_col[prop]
    formula = f"=sum({report_col}{operating_start_row}:{report_col}{operating_subtotal_row-1})"
    add_formula(operating_subtotal_row, report_col, formula)

# ACF Row (Operating + first 5 financing rows)
financing_note_rows = []
for idx in range(min(5, len(gl_accounts['Financing']))):
    financing_note_rows.append(financing_start_row + idx)

for prop in report_properties:
    report_col = property_to_report_col[prop]
    if len(financing_note_rows) >= 5:
        formula = f"={report_col}{operating_subtotal_row}+{report_col}{financing_note_rows[0]}+{report_col}{financing_note_rows[1]}+{report_col}{financing_note_rows[2]}+{report_col}{financing_note_rows[3]}+{report_col}{financing_note_rows[4]}"
    else:
        formula = f"={report_col}{operating_subtotal_row}"
    add_formula(acf_row, report_col, formula)

# Investing Activities formulas
print(" Building Investing Activities formulas...")
for idx, (gl_code, description, source_row) in enumerate(gl_accounts['Investing']):
    report_row = investing_start_row + idx
    
    for prop in report_properties:
        if prop == 'Total':
            formula = f"=SUM({first_property_col}{report_row}:{last_property_col}{report_row})"
            add_formula(report_row, total_column, formula)
        else:
            source_col = property_to_source_col.get(prop)
            if source_col:
                formula = f"='{SOURCE_SHEET_NAME}'!{source_col}{source_row}"
                report_col = property_to_report_col[prop]
                add_formula(report_row, report_col, formula)

# Investing Subtotal
for prop in report_properties:
    report_col = property_to_report_col[prop]
    formula = f"=sum({report_col}{investing_start_row}:{report_col}{investing_subtotal_row-1})"
    add_formula(investing_subtotal_row, report_col, formula)

# Financing Activities formulas
print(" Building Financing Activities formulas...")
for idx, (gl_code, description, source_row) in enumerate(gl_accounts['Financing']):
    report_row = financing_start_row + idx
    
    for prop in report_properties:
        if prop == 'Total':
            formula = f"=SUM({first_property_col}{report_row}:{last_property_col}{report_row})"
            add_formula(report_row, total_column, formula)
        else:
            source_col = property_to_source_col.get(prop)
            if source_col:
                formula = f"='{SOURCE_SHEET_NAME}'!{source_col}{source_row}"
                report_col = property_to_report_col[prop]
                add_formula(report_row, report_col, formula)

# Financing Subtotal
for prop in report_properties:
    report_col = property_to_report_col[prop]
    formula = f"=sum({report_col}{financing_start_row}:{report_col}{financing_subtotal_row-1})"
    add_formula(financing_subtotal_row, report_col, formula)

# Restricted Cash formulas
print(" Building Restricted Cash formulas...")
for idx, (gl_code, description, source_row) in enumerate(gl_accounts['Restricted']):
    report_row = restricted_start_row + idx
    
    for prop in report_properties:
        if prop == 'Total':
            formula = f"=SUM({first_property_col}{report_row}:{last_property_col}{report_row})"
            add_formula(report_row, total_column, formula)
        else:
            source_col = property_to_source_col.get(prop)
            if source_col:
                formula = f"='{SOURCE_SHEET_NAME}'!{source_col}{source_row}"
                report_col = property_to_report_col[prop]
                add_formula(report_row, report_col, formula)

# Restricted Subtotal
for prop in report_properties:
    report_col = property_to_report_col[prop]
    formula = f"=sum({report_col}{restricted_start_row}:{report_col}{restricted_subtotal_row-1})"
    add_formula(restricted_subtotal_row, report_col, formula)

# Summary Section
print(" Building Summary formulas...")
for prop in report_properties:
    report_col = property_to_report_col[prop]
    add_formula(summary_operating_row, report_col, f"={report_col}{operating_subtotal_row}")
    add_formula(summary_investing_row, report_col, f"={report_col}{investing_subtotal_row}")
    add_formula(summary_financing_row, report_col, f"={report_col}{financing_subtotal_row}")
    add_formula(summary_net_change_row, report_col, f"=SUM({report_col}{summary_operating_row}:{report_col}{summary_financing_row})")
    add_formula(summary_restricted_row, report_col, f"={report_col}{restricted_subtotal_row}")
    add_formula(summary_total_row, report_col, f"={report_col}{summary_net_change_row}+{report_col}{summary_restricted_row}")

# Reconciliation Section
print(" Building Reconciliation formulas...")
for prop in report_properties:
    report_col = property_to_report_col[prop]
    add_formula(recon_beginning_row, report_col, "0")
    add_formula(recon_net_cash_row, report_col, f"={report_col}{summary_total_row}")
    add_formula(recon_ending_row, report_col, f"=round({report_col}{recon_beginning_row}+{report_col}{recon_net_cash_row},2)")

# Bank balance row - will be updated after realignment formulas
# For now, add placeholder formulas
for prop in report_properties:
    report_col = property_to_report_col[prop]
    source_col = property_to_source_col.get(prop)
    if prop == 'Total':
        formula = f"=round(SUM({first_property_col}{recon_bank_row}:{last_property_col}{recon_bank_row}),2)"
    elif source_col:
        formula = f"=round('{BALANCE_SHEET_NAME}'!{source_col}82,2)"
    else:
        formula = "0"
    add_formula(recon_bank_row, report_col, formula)

# Difference row
for prop in report_properties:
    report_col = property_to_report_col[prop]
    add_formula(recon_difference_row, report_col, f"={report_col}{recon_ending_row}-{report_col}{recon_bank_row}")

# Cash Account Realignment formulas
print(" Building Cash Account Realignment formulas...")

# First, add realignment account formulas
for idx, (gl_code, description, bs_row) in enumerate(realignment_accounts):
    report_row = realignment_start_row + idx
    
    for prop in report_properties:
        if prop == 'Total':
            # Skip Total column for Cash Account Realignment section
            continue
        else:
            source_col = property_to_source_col.get(prop)
            if source_col:
                formula = f"='{BALANCE_SHEET_NAME}'!{source_col}{bs_row}"
                report_col = property_to_report_col[prop]
                add_formula(report_row, report_col, formula)

print(f"    Built {len(formulas_to_update)} formulas")

# Apply all formulas in one batch
print("\n Applying formulas...")

body = {
    'valueInputOption': 'USER_ENTERED',
    'data': formulas_to_update
}

service.spreadsheets().values().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body=body
).execute()

print(f"    Applied all {len(formulas_to_update)} formulas in one batch")

print(f"\n All {len(formulas_to_update)} formulas applied!")

# ============================================================================
# PHASE 5: ADJUST BANK BALANCE FORMULAS FOR REALIGNMENT
# ============================================================================

print("\n\n PHASE 5: Adjust Bank Balance Formulas")
print("-" * 80)

# Read realignment values to see which properties have non-zero values
print("\n Checking which properties have realignment values...")

# Build range for all realignment rows across all properties
if len(realignment_accounts) > 0:
    realignment_range = f"{first_property_col}{realignment_start_row}:{total_column}{realignment_end_row}"
    realignment_values = test_sheet.get(realignment_range)
    
    # Track which properties have non-zero realignment values
    properties_with_realignment = {}
    
    for prop_idx, prop in enumerate(report_properties):
        has_nonzero = False
        for row_idx in range(len(realignment_values)):
            if prop_idx < len(realignment_values[row_idx]):
                value = realignment_values[row_idx][prop_idx]
                if value and value not in ['0', '0.00', '-', '']:
                    has_nonzero = True
                    break
        
        if has_nonzero:
            properties_with_realignment[prop] = True
            print(f"   Property '{prop}' has realignment values")
    
    # Now update bank balance formulas for properties with realignment
    print("\n Updating bank balance formulas...")
    adjusted_formulas = []
    
    for prop in report_properties:
        report_col = property_to_report_col[prop]
        source_col = property_to_source_col.get(prop)
        
        if prop == 'Total':
            # Total column stays as SUM
            continue
        
        if prop in properties_with_realignment and source_col:
            # Build adjustment formula: Balance Sheet + sum of realignment rows
            realignment_sum = '+'.join([f"{report_col}{realignment_start_row + i}" 
                                       for i in range(len(realignment_accounts))])
            formula = f"=round('{BALANCE_SHEET_NAME}'!{source_col}72+{realignment_sum},2)"
            
            adjusted_formulas.append({
                'range': f"{OUTPUT_SHEET_NAME}!{report_col}{recon_bank_row}",
                'values': [[formula]]
            })
            print(f"   Adjusted {prop}: Added realignment adjustment")
    
    if adjusted_formulas:
        # Apply adjusted formulas
        body = {
            'valueInputOption': 'USER_ENTERED',
            'data': adjusted_formulas
        }
        
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body
        ).execute()
        
        print(f"\n    Updated {len(adjusted_formulas)} bank balance formulas with realignment adjustments")
    
    # Clear cells with zero values in realignment section
    print("\n Clearing zero values in realignment section...")
    cells_to_clear = []
    
    for row_idx in range(len(realignment_values)):
        report_row = realignment_start_row + row_idx
        for prop_idx, prop in enumerate(report_properties):
            if prop_idx < len(realignment_values[row_idx]):
                value = realignment_values[row_idx][prop_idx]
                # Clear if zero or empty
                if not value or value in ['0', '0.00', '-', '']:
                    report_col = property_to_report_col[prop]
                    cells_to_clear.append({
                        'range': f"{OUTPUT_SHEET_NAME}!{report_col}{report_row}",
                        'values': [['']]
                    })
    
    if cells_to_clear:
        # Clear cells in one batch
        body = {
            'valueInputOption': 'RAW',
            'data': cells_to_clear
        }
        
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body
        ).execute()
        
        print(f"    Cleared {len(cells_to_clear)} cells with zero values in one batch")
    else:
        print("     No zero values to clear")
else:
    print("     No realignment accounts found")

# ============================================================================
# PHASE 6: APPLY FORMATTING
# ============================================================================
# Formatting rules derived from baseline sheet analysis:
# - Frozen panes: 4 rows, 5 columns (freeze A:E and rows 1-4)
# - Yellow background: ONLY rows 20 and 21 (Operating Subtotal + ACF)
# - Bold text: ALL GL account rows in Column B (rows 2+)
# - Font: Arial, 12pt for title (row 2), 10pt for rest
# - Number format: Property columns (F:BC) = Accounting format _(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)
# - Alignment: Property columns (F:BC) = CENTER, Vertical = BOTTOM
# - Column widths: Get from baseline (A:BC specific sizes)
# - Borders: Top border (SOLID_MEDIUM) on subtotal rows
# - Conditional formatting: Green text if >0, Red text if <0 (on subtotal rows)
# ============================================================================

print("\n\n PHASE 6: Apply Formatting")
print("-" * 80)

yellow_color = {"red": 1.0, "green": 1.0, "blue": 0.0}
format_requests = []

# 1. Yellow background ONLY on Operating Subtotal (row 20) and ACF (row 21)
yellow_rows = [
    operating_subtotal_row,  # Row 20: Net Cash Inflow/Outflow from Operating Activities
    acf_row,                 # Row 21: Adjusted Cash Flow
]

for row in yellow_rows:
    format_requests.append({
        "repeatCell": {
            "range": {
                "sheetId": test_sheet_id,
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": 0,
                "endColumnIndex": 55  # A:BC
            },
            "cell": {"userEnteredFormat": {"backgroundColor": yellow_color}},
            "fields": "userEnteredFormat.backgroundColor"
        }
    })

print(f"    Yellow background: {len(yellow_rows)} rows (Operating Subtotal + ACF only)")

# 2. Bold text for ALL GL account rows in Column B (baseline has bold on rows 2-80)
# This includes all content rows: title, sections, GL accounts, subtotals, summary, reconciliation
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 1,  # Row 2 onwards
            "endRowIndex": 1000,  # All rows with content
            "startColumnIndex": 1,  # Column B
            "endColumnIndex": 2
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {"bold": True}
            }
        },
        "fields": "userEnteredFormat.textFormat.bold"
    }
})

print(f"    Bold text: All rows (Column B)")

# 3. Font sizes
# Title row (row 2) = 12pt
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 1,  # Row 2
            "endRowIndex": 2,
            "startColumnIndex": 1,  # Column B
            "endColumnIndex": 2
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {"fontSize": 12}
            }
        },
        "fields": "userEnteredFormat.textFormat.fontSize"
    }
})

# All other rows = 10pt
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 2,  # Row 3 onwards
            "endRowIndex": 1000,
            "startColumnIndex": 0,  # All columns
            "endColumnIndex": 55
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {"fontSize": 10}
            }
        },
        "fields": "userEnteredFormat.textFormat.fontSize"
    }
})

print(f"    Font sizes: Title=12pt, All others=10pt")

# 4. Number format for property columns (F:BC) - Accounting format
# Pattern: _(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 0,
            "endRowIndex": 1000,  # All rows
            "startColumnIndex": 5,  # Column F
            "endColumnIndex": 55  # Column BC
        },
        "cell": {
            "userEnteredFormat": {
                "numberFormat": {
                    "type": "NUMBER",
                    "pattern": '_(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)'
                }
            }
        },
        "fields": "userEnteredFormat.numberFormat"
    }
})

print(f"    Number format: Accounting format for property columns")

# 5. Alignment - Property columns (F:BC) = CENTER
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 0,
            "endRowIndex": 1000,
            "startColumnIndex": 5,  # Column F
            "endColumnIndex": 55  # Column BC
        },
        "cell": {
            "userEnteredFormat": {
                "horizontalAlignment": "CENTER"
            }
        },
        "fields": "userEnteredFormat.horizontalAlignment"
    }
})

print(f"    Alignment: CENTER for property columns")

# 6. Column widths
column_widths = [
    {"sheetId": test_sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1, "pixelSize": 100},  # A: GL Code
    {"sheetId": test_sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2, "pixelSize": 20},   # B: Blank
    {"sheetId": test_sheet_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3, "pixelSize": 300},  # C: Description
    {"sheetId": test_sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 5, "pixelSize": 20},   # D-E: Blank
    {"sheetId": test_sheet_id, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 55, "pixelSize": 90},  # F-BC: Properties
]

for width_spec in column_widths:
    format_requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": width_spec["sheetId"],
                "dimension": width_spec["dimension"],
                "startIndex": width_spec["startIndex"],
                "endIndex": width_spec["endIndex"]
            },
            "properties": {"pixelSize": width_spec["pixelSize"]},
            "fields": "pixelSize"
        }
    })

print(f"    Column widths: A=100px, B=20px, C=300px, D-E=20px, F-BC=90px")

# 7. Hide Column A (GL codes)
format_requests.append({
    "updateDimensionProperties": {
        "range": {
            "sheetId": test_sheet_id,
            "dimension": "COLUMNS",
            "startIndex": 0,  # Column A
            "endIndex": 1
        },
        "properties": {"hiddenByUser": True},
        "fields": "hiddenByUser"
    }
})

print(f"    Hidden columns: Column A (GL codes)")

# 8. Freeze panes (4 rows, 5 columns - freeze headers and GL code columns)
format_requests.append({
    "updateSheetProperties": {
        "properties": {
            "sheetId": test_sheet_id,
            "gridProperties": {
                "frozenRowCount": 4,
                "frozenColumnCount": 5
            }
        },
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
    }
})

print(f"    Freeze panes: 4 rows, 5 columns")

# 9. Font family (Arial for all cells)
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 0,
            "endRowIndex": 1000,
            "startColumnIndex": 0,
            "endColumnIndex": 55
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {"fontFamily": "Arial"}
            }
        },
        "fields": "userEnteredFormat.textFormat.fontFamily"
    }
})

print(f"    Font family: Arial")

# 10. Vertical alignment (BOTTOM for all cells)
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": 0,
            "endRowIndex": 1000,
            "startColumnIndex": 0,
            "endColumnIndex": 55
        },
        "cell": {
            "userEnteredFormat": {
                "verticalAlignment": "BOTTOM"
            }
        },
        "fields": "userEnteredFormat.verticalAlignment"
    }
})

print(f"    Vertical alignment: BOTTOM")

# 11. Borders - Top border (SOLID_MEDIUM) on subtotal rows
border_style = {
    "style": "SOLID_MEDIUM",
    "width": 2,
    "color": {"red": 0, "green": 0, "blue": 0}
}

subtotal_rows_for_borders = [
    4,  # Net Income (row 4)
    operating_subtotal_row,  # Row 20: Operating Subtotal
    investing_subtotal_row,  # Row 36: Investing Subtotal
    financing_subtotal_row,  # Row 52: Financing Subtotal
    restricted_subtotal_row,  # Row 59: Restricted Subtotal
    # ACF row REMOVED - only yellow highlight, no border
    recon_ending_row,  # Ending Cash in Bank Balance (reconciliation row)
]

for row in subtotal_rows_for_borders:
    format_requests.append({
        "repeatCell": {
            "range": {
                "sheetId": test_sheet_id,
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": 5,  # Column F
                "endColumnIndex": 55  # Column BC
            },
            "cell": {
                "userEnteredFormat": {
                    "borders": {"top": border_style}
                }
            },
            "fields": "userEnteredFormat.borders.top"
        }
    })

print(f"    Borders: Top borders on {len(subtotal_rows_for_borders)} subtotal rows")

# 12. Bold formatting for reconciliation rows (property columns F:BC)
# Ending Balance, Bank Balance, and Difference rows
recon_rows_bold = [
    recon_ending_row,  # Ending Cash in Bank Balance
    recon_bank_row,    # Cash in Bank Balance (As per Balance Sheet)
    recon_difference_row,  # Difference
]

for row in recon_rows_bold:
    format_requests.append({
        "repeatCell": {
            "range": {
                "sheetId": test_sheet_id,
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": 5,  # Column F
                "endColumnIndex": 55  # Column BC
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True}
                }
            },
            "fields": "userEnteredFormat.textFormat.bold"
        }
    })

print(f"    Bold reconciliation rows: {len(recon_rows_bold)} rows (property columns)")

# 13. Blue color for Difference row (Column C and property columns)
blue_color = {"red": 0, "green": 0, "blue": 1.0}

# Column C (description)
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": recon_difference_row - 1,
            "endRowIndex": recon_difference_row,
            "startColumnIndex": 2,  # Column C
            "endColumnIndex": 3
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {
                    "bold": True,
                    "foregroundColor": blue_color
                }
            }
        },
        "fields": "userEnteredFormat.textFormat"
    }
})

# Property columns (F:BC)
format_requests.append({
    "repeatCell": {
        "range": {
            "sheetId": test_sheet_id,
            "startRowIndex": recon_difference_row - 1,
            "endRowIndex": recon_difference_row,
            "startColumnIndex": 5,  # Column F
            "endColumnIndex": 55  # Column BC
        },
        "cell": {
            "userEnteredFormat": {
                "textFormat": {
                    "foregroundColor": blue_color
                }
            }
        },
        "fields": "userEnteredFormat.textFormat.foregroundColor"
    }
})

print(f"    Blue bold text: Difference row (Column C + property columns)")

# Apply all formatting in one batch
service.spreadsheets().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body={"requests": format_requests}
).execute()

print(f"    All formatting applied ({len(format_requests)} format requests)")

# 14. Conditional formatting (green if >0, red if <0) - Apply AFTER base formatting
# Conditional rules for subtotal rows
conditional_rules = []

green_color = {"red": 0.21960784, "green": 0.4627451, "blue": 0.11372549}
red_color = {"red": 1.0, "green": 0, "blue": 0}

subtotal_rows_for_conditional = [
    4,  # Net Income
    operating_subtotal_row,  # Row 20
    investing_subtotal_row,  # Row 36
    financing_subtotal_row,  # Row 52
    restricted_subtotal_row,  # Row 59
    acf_row + 1,  # Summary row after ACF (row 65)
]

for row in subtotal_rows_for_conditional:
    # Green if >0
    conditional_rules.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": test_sheet_id,
                    "startRowIndex": row - 1,
                    "endRowIndex": row,
                    "startColumnIndex": 5,  # Column F
                    "endColumnIndex": 55  # Column BC
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": f"=(F{row}>0)"}]
                    },
                    "format": {
                        "textFormat": {
                            "foregroundColor": green_color
                        }
                    }
                }
            },
            "index": 0
        }
    })
    
    # Red if <0
    conditional_rules.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": test_sheet_id,
                    "startRowIndex": row - 1,
                    "endRowIndex": row,
                    "startColumnIndex": 5,  # Column F
                    "endColumnIndex": 55  # Column BC
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": f"=(F{row}<0)"}]
                    },
                    "format": {
                        "textFormat": {
                            "foregroundColor": red_color
                        }
                    }
                }
            },
            "index": 0
        }
    })

service.spreadsheets().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body={"requests": conditional_rules}
).execute()

print(f"    Conditional formatting: Green (>0), Red (<0) on {len(subtotal_rows_for_conditional)} rows")

# ============================================================================
# PHASE 7: REORDER SHEETS
# ============================================================================

print("\n\n PHASE 7: Reorder Sheets")
print("-" * 80)

# Get current sheet metadata
sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
sheet_map = {}
cash_needs_sheet = None
summary_page_sheet = None

for sheet_props in sheet_metadata['sheets']:
    sheet_title = sheet_props['properties']['title']
    sheet_id = sheet_props['properties']['sheetId']
    sheet_map[sheet_title] = sheet_id
    
    # Find Cash Needs sheet (regardless of date suffix)
    if sheet_title.startswith('Cash Needs'):
        cash_needs_sheet = sheet_title
    
    # Find Summary page (case-insensitive)
    if sheet_title.lower() == 'summary page':
        summary_page_sheet = sheet_title

# Define desired sheet order (include BOTH monthly and YTD reports)
desired_order = [
    summary_page_sheet or 'Summary page',        # Use actual name if found
    cash_needs_sheet or 'Cash Needs @9.05.2025', # Use actual name if found
    f"Cash Flow Report (All) - {MONTH}",         # Monthly report
    f"Cash Flow Report (All) - YTD.{MONTH}",     # YTD report
    f"Cash Flow ({MONTH})",                       # Monthly source
    f"Cash Flow (YTD-{MONTH})",                   # YTD source
    f"Balance Sheet ({MONTH})",                   # Balance Sheet
    'Property Status Tracker',
]

# Build reorder requests
reorder_requests = []
sheets_to_order = []

for new_index, sheet_title in enumerate(desired_order):
    if sheet_title in sheet_map:
        sheet_id = sheet_map[sheet_title]
        reorder_requests.append({
            'updateSheetProperties': {
                'properties': {
                    'sheetId': sheet_id,
                    'index': new_index
                },
                'fields': 'index'
            }
        })
        sheets_to_order.append(sheet_title)

# Apply reordering
if reorder_requests:
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={'requests': reorder_requests}
    ).execute()
    print(f"    Reordered {len(reorder_requests)} sheets")
    print(f"    Order: {' → '.join(sheets_to_order)}")
else:
    print("    No sheets to reorder")

# ============================================================================
# COMPLETION
# ============================================================================

print("\n" + "=" * 80)
print(" PRODUCTION CASH FLOW REPORT GENERATED")
print("=" * 80)
print(f"\n📊 Sheet created: '{OUTPUT_SHEET_NAME}'")
print(f" Structure: {len(structure_updates)} cells (headers, labels, descriptions)")
print(f" Formulas: {len(formulas_to_update)} formulas")
print(f" Bank balance adjustments: {len(adjusted_formulas) if len(realignment_accounts) > 0 else 0} properties adjusted")
print(f" Formatting: Yellow highlighting applied")
print(f"\n📊 GL Accounts by Category:")
print(f"   Operating:  {len(gl_accounts['Operating'])} accounts (rows {operating_start_row}-{operating_subtotal_row-1})")
print(f"   Investing:  {len(gl_accounts['Investing'])} accounts (rows {investing_start_row}-{investing_subtotal_row-1})")
print(f"   Financing:  {len(gl_accounts['Financing'])} accounts (rows {financing_start_row}-{financing_subtotal_row-1})")
print(f"   Restricted: {len(gl_accounts['Restricted'])} accounts (rows {restricted_start_row}-{restricted_subtotal_row-1})")
print(f"\n Cash Account Realignment:")
print(f"   {len(realignment_accounts)} accounts (rows {realignment_start_row}-{realignment_end_row})")
print("\n Features:")
print("    GL codes and descriptions trimmed")
print("    Dynamic discovery from SOURCE adjustments")
print("    Rule-based auto-categorization")
print("    Cash Account Realignment from Balance Sheet")
print("    Bank balance adjusted for realignment values")
print("    Fresh values calculated from current data")
print("    Sheet ordering: Summary → Cash Needs → Cash Flow Reports → Source Data")
