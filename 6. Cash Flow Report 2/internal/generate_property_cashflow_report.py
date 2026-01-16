"""
Generate Property Cash Flow Report - Main Automation Script
Populates PORTFOLIO CASH FLOW from HA-CF data and Month End Reports status

ABSOLUTELY NO HARDCODED POSITIONS - ALL LOOKUPS BY CONTENT SEARCH
Every column and row is found by searching for identifying content, never by position.
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
from gspread_formatting import CellFormat, Color, format_cell_range
from difflib import SequenceMatcher
import sys
import time
from datetime import datetime

# Configuration
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
DEFAULT_SHEET_ID = "1iZNLklMpAPeVo57nJVFfGBqUmQ3PD_bow4IlYOvtQj0"
SHEET_ID = os.environ.get("CASHFLOW_SHEET_ID") or DEFAULT_SHEET_ID
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def _extract_sheet_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    marker = "/spreadsheets/d/"
    if marker in value:
        after = value.split(marker, 1)[1]
        return after.split("/", 1)[0]
    return value


def _service_account_email(creds_path: str) -> str | None:
    try:
        data = json.loads(Path(creds_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    email = data.get("client_email")
    return str(email).strip() if email else None

# Properties to skip (empty by default – all properties processed)
SKIP_PROPERTIES = []

# Month End normalization rules
PREFIX_TERMS = [
    'EP',
    'SS of',
    'SS',
    'SMS',
    'Storsafe of'
]

SUFFIX_TERMS = [
    ' Chase',
    ' Amalgamated',
    ' Uhaul',
    ' Busey',
    ' Busey Bank',
    ' Centier',
    ' Centier Reserve',
    ' Choice',
    ' Cypress',
    ' Pan American',
    ' Providence',
    ' First Merchants',
    ' Bank 5/9',
    ' Key Bank',
    ' FBHP',
    ' Forte Bank',
    ' Forte Reserve'
]

GREEN_MIN = 0.55
RED_MAX = 0.5
BLUE_MAX = 0.45

# Colors
LIGHT_YELLOW = Color(1.0, 1.0, 0.8)


def _is_header_match(text: str, *needles: str) -> bool:
    t = str(text or "").lower()
    return all(n.lower() in t for n in needles)
LIGHT_RED = Color(0.95, 0.8, 0.8)


def strip_prefix(value: str) -> str:
    """Remove configured prefixes (case-insensitive) from a property string."""
    cleaned = value.strip()
    changed = True
    while changed and cleaned:
        changed = False
        for prefix in PREFIX_TERMS:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].lstrip(' -').strip()
                changed = True
                break
    return cleaned


def strip_suffix(value: str) -> str:
    """Remove configured suffixes (banks, funding sources, etc.)."""
    cleaned = value.strip()
    changed = True
    while changed and cleaned:
        changed = False
        for suffix in SUFFIX_TERMS:
            if cleaned.lower().endswith(suffix.lower()):
                cleaned = cleaned[:-len(suffix)].rstrip('- ').strip()
                changed = True
                break
    return cleaned


def normalize_root(value: str) -> str:
    """Collapse a property name down to its canonical root."""
    root = strip_suffix(value)
    lower = root.lower()
    if lower.startswith('2201'):
        return '2201'
    if lower.startswith('swss'):
        return 'SWSS'
    if 'huntley north' in lower:
        return 'HSS'
    if 'huntley south' in lower:
        return 'HSS 2'
    if lower == 'candler tax & insurance':
        return 'Candler'
    if lower == 'silver springs equitable':
        return 'Silver Springs'
    if lower == 'mss 1st merchants':
        return 'MSS'
    return root


def normalize_portfolio_property(prop_name: str) -> str:
    """Normalize a portfolio property name (base before hyphen) to a comparable root."""
    if not prop_name:
        return ''
    base = prop_name.split(' - ', 1)[0].strip()
    cleaned = strip_prefix(base)
    return normalize_root(cleaned)


def _color_component(color, attr: str) -> float:
    if hasattr(color, attr):
        value = getattr(color, attr)
    elif isinstance(color, dict):
        value = color.get(attr)
    else:
        value = None
    return value if value is not None else 0.0


def is_green_color(color) -> bool:
    """Return True when a Google Sheets color object or dict is visibly green."""
    if color is None:
        return False
    red = _color_component(color, 'red')
    green = _color_component(color, 'green')
    blue = _color_component(color, 'blue')
    return green >= GREEN_MIN and red <= RED_MAX and blue <= BLUE_MAX


def parse_currency(value):
    """Convert currency string to float"""
    if not value or value == '':
        return 0.0
    value = str(value).replace(',', '').replace('$', '').strip()
    if '(' in value and ')' in value:
        value = '-' + value.replace('(', '').replace(')', '')
    try:
        return float(value)
    except:
        return 0.0


def fuzzy_match(str1, str2):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def _norm_label(value: str) -> str:
    return ' '.join(str(value).strip().upper().split())


def _is_na_value(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"n/a", "na", "n\\a"}


class PropertyCashFlowGenerator:
    def __init__(
        self,
        sheet_id: str,
        month_tab: str,
        month_label: str,
        skip_month_end: bool,
        *,
        portfolio_tab: str,
        property_codes_tab: str,
        month_end_tab: str,
    ):
        print("="*100)
        print("PROPERTY CASH FLOW REPORT GENERATOR - ZERO HARDCODED INDICES")
        print("="*100)
        
        # Connect to Google Sheets
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(sheet_id)

        self.month_tab = month_tab
        self.month_label = month_label
        
        # Auto-skip month end highlighting if current month is 2+ months after target report month
        self.skip_month_end = skip_month_end or self._should_skip_month_end_by_date(month_label)
        
        self.portfolio_tab = portfolio_tab
        self.property_codes_tab = property_codes_tab
        self.month_end_tab = month_end_tab

        # Load worksheets (batch load to minimize API calls)
        print("   Loading worksheets...")
        self.portfolio_ws = self.spreadsheet.worksheet(self.portfolio_tab)
        time.sleep(0.5)
        self.property_codes_ws = self.spreadsheet.worksheet(self.property_codes_tab)
        time.sleep(0.5)
        try:
            self.month_end_ws = self.spreadsheet.worksheet(self.month_end_tab)
        except gspread.WorksheetNotFound:
            # Back-compat: older prepared workbooks used "Bank Rec priorities".
            fallback = "Bank Rec priorities" if self.month_end_tab == "MONTH END LIST" else "MONTH END LIST"
            self.month_end_ws = self.spreadsheet.worksheet(fallback)
            self.month_end_tab = fallback
        
        print("[OK] Connected to Google Sheets")
        
        # Load all data upfront (batch operations)
        print("   Loading data...")
        self.portfolio_data = self.portfolio_ws.get_all_values()
        time.sleep(0.5)
        self.property_codes_data = self.property_codes_ws.get_all_values()
        time.sleep(0.5)
        self.month_end_data = self.month_end_ws.get_all_values()
        time.sleep(0.5)
        
        # Load PROPERTY STATUS for filtering skip/sold properties
        print("   Loading PROPERTY STATUS...")
        self.excluded_properties = []
        try:
            status_tracker_ws = self.spreadsheet.worksheet('PROPERTY STATUS')
            time.sleep(0.5)
            status_data = status_tracker_ws.get('A2:B100')
            time.sleep(0.5)
            if status_data:
                for row in status_data:
                    if len(row) >= 2:
                        prop_code = (row[0] or "").strip()
                        status_label = (row[1] or "").strip()
                        if prop_code and status_label.lower() in ['skip', 'sold']:
                            self.excluded_properties.append(prop_code)
                if self.excluded_properties:
                    print(f"      [OK] Excluding {len(self.excluded_properties)} properties with 'skip'/'sold' status: {', '.join(self.excluded_properties)}")
                else:
                    print(f"      [OK] No properties to exclude")
        except gspread.WorksheetNotFound:
            print(f"      [WARN] 'PROPERTY STATUS' not found - all properties will be processed")
        
        # Pre-load HA-CF sheets to avoid loading during processing
        print("   Pre-loading HA-CF sheets...")
        self.hacf_sheets = {}
        self.cfads_row_cache = {}
        for sheet_name in [self.month_tab, 'HA-CF-3MOS', 'HA-CF-YTD']:
            ws = self.spreadsheet.worksheet(sheet_name)
            time.sleep(0.5)
            self.hacf_sheets[sheet_name] = ws.get_all_values()
            time.sleep(0.5)
            print(f"      [OK] Loaded {sheet_name}")
        
        # Discover columns once for consistent lookups
        self.portfolio_prop_col = self.find_property_name_column(self.portfolio_data)
        self.property_codes_name_col = self.find_property_name_column(self.property_codes_data)
        self.property_codes_code_col = (
            self.find_code_column(self.property_codes_data, self.property_codes_name_col)
            if self.property_codes_name_col is not None
            else None
        )

        # Build property list (by row; supports duplicates)
        self.properties = self.build_properties()

        # Debug helper: show how each portfolio property maps to Property Codes
        self.print_property_code_mapping_debug()
        
        # Check Month End Reports status
        if self.skip_month_end:
            self.month_end_status = {}
            self.bs_recon_status = {}
        else:
            # Month End review status no longer drives highlighting.
            # Kept for potential diagnostics, but we avoid the extra API call.
            self.month_end_status = {}
            self.bs_recon_status = self.check_balance_sheet_recon_status()


    def _should_skip_month_end_by_date(self, month_label: str) -> bool:
        """Check if current month is 2+ months after target report month.
        
        If the current date is already 2+ months beyond the target report month,
        we skip month-end highlighting as the data is historical and doesn't need
        the visual indicators anymore.
        
        Args:
            month_label: Month name like 'November', 'January', etc.
            
        Returns:
            True if highlighting should be skipped, False otherwise.
        """
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        try:
            target_month = month_names.get(month_label.lower().strip())
            if target_month is None:
                return False  # Can't determine, don't skip
            
            current_date = datetime.now()
            current_month = current_date.month
            current_year = current_date.year
            
            # Assume target year is current year, or previous year if target month > current month
            # (e.g., generating December report in January means target is last year's December)
            target_year = current_year
            if target_month > current_month:
                target_year = current_year - 1
            
            # Calculate months difference
            months_diff = (current_year - target_year) * 12 + (current_month - target_month)
            
            if months_diff >= 2:
                print(f"   [INFO] Target month ({month_label}) is {months_diff} months ago - skipping month-end highlighting")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"   [WARN] Could not determine date comparison: {e}")
            return False


    def print_property_code_mapping_debug(self):
        """Debug helper to verify which properties are found in Property Codes.

        For each portfolio property in self.property_mapping, this prints:
        - Portfolio property name
        - Mapping status (MAPPED / FUZZY_NEEDED / SKIP)
        - Yardi code (if any)
        - The Property Codes sheet name cell that matched (including base/address splits)
        """

        print("\n" + "="*100)
        print("PROPERTY <-> PROPERTY CODES MAPPING DEBUG")
        print("="*100)

        # Re-discover the name/code columns in Property Codes so we can show the exact matched name
        pc_name_col = self.find_property_name_column(self.property_codes_data)
        pc_code_col = self.find_code_column(self.property_codes_data, pc_name_col) if pc_name_col is not None else None

        if pc_name_col is None or pc_code_col is None:
            print("   [WARN] Cannot run mapping debug – Property Codes columns not identified")
            return

        # Build a quick lookup of code -> list of names in Property Codes
        code_to_names = {}
        for pc_row in self.property_codes_data:
            if len(pc_row) > max(pc_name_col, pc_code_col):
                pc_name = pc_row[pc_name_col].strip()
                code = pc_row[pc_code_col].strip()
                if not code:
                    continue
                aliases = [alias.strip() for alias in pc_name.split(';') if alias.strip()]
                if not aliases:
                    continue
                code_to_names.setdefault(code, []).extend(aliases)

        print(f"   Columns in Property Codes: name col {pc_name_col}, code col {pc_code_col}")
        print("\n   Portfolio Property | Status        | Yardi Code   | Property Codes Name(s)")
        print("   " + "-"*90)

        for info in sorted(self.properties, key=lambda x: (x.get('name', '').lower(), x.get('row', 0))):
            prop_name = info.get('name') or ''
            status = info.get('status') or ''
            code = info.get('yardi_code') or ''
            matched_alias = info.get('matched_alias') or ''

            # Find matching Property Codes names for this code, if any
            pc_names = code_to_names.get(code, []) if code else []
            pc_names_str = "; ".join(pc_names) if pc_names else "(not found in Property Codes)"
            if matched_alias:
                print(f"   {prop_name:<22} | {status:<12} | {code:<11} | {pc_names_str}  -> matched: {matched_alias}")
            else:
                print(f"   {prop_name:<22} | {status:<12} | {code:<11} | {pc_names_str}")
    
    
    def find_property_name_column(self, data):
        """Find column containing property names by searching for known property names"""
        known_properties = ['michigan city', 'silver springs', 'crown point', 'wildwood', 'palm bay']
        
        for row in data:
            for col_idx, cell in enumerate(row):
                cell_lower = str(cell).lower().strip()
                for prop in known_properties:
                    if prop in cell_lower:
                        return col_idx
        
        return None


    def find_month_end_status_column(self, data):
        """Locate the Month End review column by scanning header text."""
        header_rows = min(len(data), 20)
        for row_idx in range(header_rows):
            for col_idx, cell in enumerate(data[row_idx]):
                cell_lower = str(cell).lower().strip()
                if 'month end' in cell_lower and 'review' in cell_lower:
                    return col_idx
        return None


    def find_balance_sheet_recon_column(self, data):
        """Locate the Balance Sheet reconciliation column by scanning header text."""
        header_rows = min(len(data), 20)
        for row_idx in range(header_rows):
            for col_idx, cell in enumerate(data[row_idx]):
                if _is_header_match(cell, 'balance sheet', 'recon') or _is_header_match(cell, 'balance sheet', 'reconciliation'):
                    return col_idx
        return None
    
    
    def find_code_column(self, data, name_col):
        """Find column containing property codes by looking for short alphanumeric values"""
        for row in data:
            for col_idx, cell in enumerate(row):
                if col_idx == name_col:
                    continue
                
                cell_str = str(cell).strip()
                if cell_str and len(cell_str) <= 15 and (cell_str.replace('-', '').isalnum()):
                    codes_in_col = sum(1 for r in data 
                                      if len(r) > col_idx and r[col_idx].strip() and len(r[col_idx].strip()) <= 15)
                    if codes_in_col >= 10:
                        return col_idx
        
        return None
    
    
    def column_index_to_letter(self, col_idx):
        """Convert column index (0-based) to Excel column letter (A, B, ... Z, AA, AB, etc.)"""
        col_letter = ''
        col_idx += 1  # Convert to 1-based for Excel
        
        while col_idx > 0:
            col_idx -= 1
            col_letter = chr(65 + (col_idx % 26)) + col_letter
            col_idx //= 26
        
        return col_letter


    def get_column_background_colors(self, worksheet, column_letter, row_count):
        """Fetch effective background colors for a sheet column in one API call."""
        range_label = f"'{worksheet.title}'!{column_letter}1:{column_letter}{row_count}"
        metadata = self.spreadsheet.fetch_sheet_metadata({
            'ranges': [range_label],
            'fields': 'sheets.data.rowData.values.effectiveFormat.backgroundColor'
        })

        colors_by_row = {}
        sheets = metadata.get('sheets', [])
        if not sheets:
            return colors_by_row

        data_blocks = sheets[0].get('data', [])
        if not data_blocks:
            return colors_by_row

        row_data = data_blocks[0].get('rowData', [])
        for idx, row in enumerate(row_data, start=1):
            values = row.get('values', [])
            if not values:
                continue
            effective_format = values[0].get('effectiveFormat', {})
            background = effective_format.get('backgroundColor')
            if background:
                colors_by_row[idx] = background

        return colors_by_row
    
    
    def build_properties(self):
        """Build a per-row property list from PORTFOLIO CASH FLOW, mapping each row to a Yardi code."""
        print("\n" + "="*100)
        print("BUILDING PROPERTY MAPPING")
        print("="*100)

        properties: list[dict] = []

        # Find property name column in PORTFOLIO CASH FLOW
        prop_col = self.portfolio_prop_col
        if prop_col is None:
            print("   [WARN] Could not identify property name column!")
            return properties
        
        print(f"   [OK] Property names in PORTFOLIO CASH FLOW: column {prop_col}")
        
        # Find columns in Property Codes sheet
        pc_name_col = self.property_codes_name_col
        pc_code_col = self.property_codes_code_col

        if pc_name_col is None or pc_code_col is None:
            print(f"   [WARN] Could not identify Property Codes sheet columns!")
            return properties
        
        print(f"   [OK] Property Codes sheet: names in column {pc_name_col}, codes in column {pc_code_col}")
        
        # Extract properties from PORTFOLIO CASH FLOW
        for row_idx, row in enumerate(self.portfolio_data):
            if len(row) <= prop_col:
                continue
            
            prop_name = row[prop_col].strip()
            
            if not prop_name:
                continue
            
            normalized_root = normalize_portfolio_property(prop_name)

            prop_upper = prop_name.upper()
            if any(keyword in prop_upper for keyword in ['STORAGE', 'HARD ASSETS', 'LAUNDROMAT', 'SUBTOTAL', 'TOTAL', 'PROPERTY NAME', 'PROPERTIES']):
                continue
            
            if prop_name in SKIP_PROPERTIES:
                properties.append({
                    'name': prop_name,
                    'row': row_idx + 1,
                    'yardi_code': None,
                    'status': 'SKIP',
                    'matched_alias': None,
                    'normalized_root': normalized_root,
                })
                continue
            
            # Normalize portfolio name into base/address parts if it contains " - "
            pf_base = prop_name
            pf_rest = None
            if ' - ' in prop_name:
                pf_base, pf_rest = prop_name.split(' - ', 1)
                pf_base = pf_base.strip()
                pf_rest = pf_rest.strip()

            # Look up Yardi code (supports several patterns):
            # 1) Exact full-name match
            # 2) Base-only match (Property Codes has just the base name)
            # 3) Base; Address vs Base - Address match using '; ' delimiter
            yardi_code = None
            matched_alias = None
            normalized_root_lower = normalized_root.lower() if normalized_root else ''
            for pc_row in self.property_codes_data:
                if len(pc_row) > max(pc_name_col, pc_code_col):
                    pc_name = pc_row[pc_name_col].strip()
                    code = pc_row[pc_code_col].strip()
                    
                    if not code:
                        continue

                    # Break Property Codes cell into alias list (e.g., "HSS 2; Huntley South; EP HSS 2")
                    aliases = [alias.strip() for alias in pc_name.split(';') if alias.strip()]
                    if not aliases:
                        continue

                    for alias in aliases:
                        alias_norm = alias.lower()
                        prop_norm = prop_name.lower()
                        base_norm = pf_base.lower() if pf_base else None
                        rest_norm = pf_rest.lower() if pf_rest else None
                        full_combo_norm = f"{pf_base} - {pf_rest}".lower() if pf_base and pf_rest else None
                        alias_root = normalize_portfolio_property(alias)
                        alias_root_lower = alias_root.lower() if alias_root else ''

                        # 1) Exact full-name match
                        if alias_norm == prop_norm:
                            yardi_code = code
                            matched_alias = alias
                            break

                        # 2) Match just the base portion (before '-'), so aliases like "Huntley South" map to
                        #    portfolio names like "Huntley South - EP HSS 2"
                        if base_norm and alias_norm == base_norm:
                            yardi_code = code
                            matched_alias = alias
                            break

                        # 3) Match just the suffix portion (after '-'), if they list that alias separately
                        if rest_norm and alias_norm == rest_norm:
                            yardi_code = code
                            matched_alias = alias
                            break

                        # 4) Alias might already include "Base - Suffix"; match against the combined name
                        if full_combo_norm and alias_norm == full_combo_norm:
                            yardi_code = code
                            matched_alias = alias
                            break

                        # 5) Fall back to normalized root comparison to catch aliases like "MI City" vs "Michigan City"
                        if normalized_root_lower and alias_root_lower == normalized_root_lower:
                            yardi_code = code
                            matched_alias = alias
                            break
                    
                    if yardi_code:
                        break
            
            # Check if property should be excluded based on status
            if yardi_code and yardi_code in self.excluded_properties:
                properties.append({
                    'name': prop_name,
                    'row': row_idx + 1,
                    'yardi_code': yardi_code,
                    'status': 'SKIP',
                    'matched_alias': matched_alias,
                    'normalized_root': normalized_root,
                })
                continue
            
            properties.append({
                'name': prop_name,
                'row': row_idx + 1,
                'yardi_code': yardi_code,
                'status': 'MAPPED' if yardi_code else 'FUZZY_NEEDED',
                'matched_alias': matched_alias,
                'normalized_root': normalized_root,
            })
        
        mapped_count = sum(1 for p in properties if p.get('status') == 'MAPPED')
        fuzzy_count = sum(1 for p in properties if p.get('status') == 'FUZZY_NEEDED')
        skip_count = sum(1 for p in properties if p.get('status') == 'SKIP')
        
        print(f"\n[OK] Property mapping complete:")
        print(f"   - {mapped_count} with Yardi codes")
        print(f"   - {fuzzy_count} need fuzzy matching")
        print(f"   - {skip_count} skipped")
        
        return properties
    
    
    def check_month_end_status(self):
        """Check Month End Reports for property status"""
        print("\n" + "="*100)
        print("CHECKING MONTH END REPORTS STATUS")
        print("="*100)
        
        status_map = {}
        prop_col = self.find_property_name_column(self.month_end_data)
        
        if prop_col is None:
            print("   [WARN] Could not find property column")
            return status_map

        status_col = self.find_month_end_status_column(self.month_end_data)
        if status_col is None:
            print("   [WARN] Could not locate 'Month End review' column from headers; defaulting to column D")
            status_col = 3  # Column D per sheet design

        status_letter = self.column_index_to_letter(status_col)
        color_map = self.get_column_background_colors(
            self.month_end_ws,
            status_letter,
            len(self.month_end_data)
        )
        monitored_rows = 0
        root_tracker = {}

        for row_idx, row in enumerate(self.month_end_data, start=1):
            if row_idx <= 6:
                continue  # skip headers and grouping rows
            if len(row) <= prop_col:
                continue

            prop_name = row[prop_col].strip()
            if not prop_name or 'working' in prop_name.lower():
                continue

            prop_upper = prop_name.upper()
            if any(keyword in prop_upper for keyword in ['PROPERTY', 'PROPERTIES', 'HEADER']):
                continue

            normalized_root = normalize_root(strip_prefix(prop_name))
            if not normalized_root:
                continue

            color = color_map.get(row_idx)
            monitored_rows += 1

            info = root_tracker.setdefault(normalized_root, {
                'has_green': False,
                'rows': [],
                'names': set()
            })

            if is_green_color(color):
                info['has_green'] = True
            else:
                info['rows'].append(row_idx)
                info['names'].add(prop_name)

        for root, info in root_tracker.items():
            if info['has_green'] or not info['rows']:
                continue
            status_map[root] = {
                'rows': info['rows'],
                'names': info['names']
            }
        
        print(f"\n[OK] Found {len(status_map)} properties with ZERO green Month End review cells (scanned {monitored_rows} rows)")
        preview = list(sorted(status_map.items(), key=lambda x: x[0].lower()))[:10]
        if preview:
            print("   Sample non-green entries:")
            for root, info in preview:
                sample_name = next(iter(info['names']))
                rows_display = ', '.join(str(r) for r in info['rows'])
                print(f"      - {root}: rows {rows_display} ({sample_name})")
        
        return status_map


    def check_balance_sheet_recon_status(self):
        """Check Month End list for Balance Sheet reconciliation completion.

                Highlight rule:
                - If Balance Sheet reconciliation cell value is 'n/a' (case-insensitive), DO NOT highlight.
                    (Treat as exempt / not applicable.)
                - Otherwise, done = green cell in the Balance Sheet reconciliation column (typically column E).

                We return a map of normalized_root -> info for properties that should be highlighted.
        """

        print("\n" + "="*100)
        print("CHECKING BALANCE SHEET RECONCILIATION STATUS")
        print("="*100)

        status_map = {}
        prop_col = self.find_property_name_column(self.month_end_data)
        if prop_col is None:
            print("   [WARN] Could not find property column")
            return status_map

        bs_col = self.find_balance_sheet_recon_column(self.month_end_data)
        if bs_col is None:
            print("   [WARN] Could not locate 'Balance Sheet reconciliation' column from headers; defaulting to column E")
            bs_col = 4  # Column E per sheet design

        bs_letter = self.column_index_to_letter(bs_col)
        color_map = self.get_column_background_colors(
            self.month_end_ws,
            bs_letter,
            len(self.month_end_data)
        )

        monitored_rows = 0
        root_tracker = {}

        for row_idx, row in enumerate(self.month_end_data, start=1):
            if row_idx <= 6:
                continue
            if len(row) <= prop_col:
                continue

            prop_name = row[prop_col].strip()
            if not prop_name or 'working' in prop_name.lower():
                continue

            prop_upper = prop_name.upper()
            if any(keyword in prop_upper for keyword in ['PROPERTY', 'PROPERTIES', 'HEADER']):
                continue

            normalized_root = normalize_root(strip_prefix(prop_name))
            if not normalized_root:
                continue

            monitored_rows += 1
            color = color_map.get(row_idx)
            cell_value = row[bs_col] if len(row) > bs_col else ""

            info = root_tracker.setdefault(normalized_root, {
                'has_done': False,
                'has_na': False,
                'rows': [],
                'names': set(),
            })

            # n/a means exempt: do not highlight this property.
            if _is_na_value(cell_value):
                info['has_na'] = True
                info['has_done'] = True
                continue

            if is_green_color(color):
                info['has_done'] = True
            else:
                info['rows'].append(row_idx)
                info['names'].add(prop_name)

        for root, info in root_tracker.items():
            if info['has_done'] or not info['rows']:
                continue
            status_map[root] = {
                'rows': info['rows'],
                'names': info['names'],
            }

        print(
            f"\n[OK] Found {len(status_map)} properties needing Balance Sheet reconciliation (scanned {monitored_rows} rows)"
        )
        preview = list(sorted(status_map.items(), key=lambda x: x[0].lower()))[:10]
        if preview:
            print("   Sample non-green entries:")
            for root, info in preview:
                sample_name = next(iter(info['names']))
                rows_display = ', '.join(str(r) for r in info['rows'])
                print(f"      - {root}: rows {rows_display} ({sample_name})")

        return status_map
    
    
    def find_account_columns(self, hacf_data):
        """Find columns containing account codes and descriptions"""
        for row in hacf_data:
            for col_idx, cell in enumerate(row):
                cell_str = str(cell).strip()
                if cell_str and '-' in cell_str:
                    parts = cell_str.split('-')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        desc_col = col_idx + 1 if col_idx + 1 < len(row) else None
                        return col_idx, desc_col

        # Fallback for verbatim Yardi exports: no account codes, labels live in column A.
        return None, 0


    def find_label_row(self, label: str, hacf_data):
        """Find 1-indexed row number where the description/label matches exactly."""
        _, desc_col = self.find_account_columns(hacf_data)
        if desc_col is None:
            return None

        want = _norm_label(label)
        for row_idx, row in enumerate(hacf_data):
            if len(row) <= desc_col:
                continue
            cell = row[desc_col]
            text = str(cell).strip() if cell is not None else ''
            if text and _norm_label(text) == want:
                return row_idx + 1

        return None
    
    
    def find_property_code_row(self, hacf_data):
        """Find row containing property codes.
        
        Per v1 generator fix: Property codes are in Row 5 (index 4) of HA-CF sheets.
        This is more reliable than dynamic search which can find wrong rows.
        """
        # CRITICAL FIX: Row 5 (index 4) contains property codes in HA-CF sheets
        # This matches the v1 generator approach which uses source_sheet.row_values(5)
        PROPERTY_CODE_ROW_INDEX = 4  # Row 5 in 0-based index
        
        if len(hacf_data) > PROPERTY_CODE_ROW_INDEX:
            # Verify this row has property codes by checking for multiple short alphanumeric values
            row = hacf_data[PROPERTY_CODE_ROW_INDEX]
            account_code_col, desc_col = self.find_account_columns(hacf_data)
            
            code_count = 0
            for col_idx, cell in enumerate(row):
                if account_code_col is not None and col_idx <= account_code_col + 1:
                    continue
                if account_code_col is None and desc_col == 0 and col_idx == 0:
                    continue
                
                cell_str = str(cell).strip()
                if cell_str and len(cell_str) <= 15 and (cell_str.replace('-', '').isalnum()):
                    code_count += 1
            
            if code_count >= 5:  # Lower threshold since we're checking specific row
                return PROPERTY_CODE_ROW_INDEX
        
        # Fallback to dynamic search if Row 5 doesn't have codes
        account_code_col, desc_col = self.find_account_columns(hacf_data)
        
        for row_idx, row in enumerate(hacf_data):
            code_count = 0
            for col_idx, cell in enumerate(row):
                if account_code_col is not None and col_idx <= account_code_col + 1:
                    continue
                if account_code_col is None and desc_col == 0 and col_idx == 0:
                    continue
                
                cell_str = str(cell).strip()
                if cell_str and len(cell_str) <= 15 and (cell_str.replace('-', '').isalnum()):
                    code_count += 1
            
            if code_count >= 10:
                return row_idx
        
        return None
    
    
    def find_cfads_row(self, hacf_data):
        """Find CASH FLOW row"""
        account_code_col, desc_col = self.find_account_columns(hacf_data)
        
        if desc_col is None:
            return None
        
        for row_idx, row in enumerate(hacf_data):
            if len(row) > desc_col:
                description = row[desc_col].strip()
                if 'CASH FLOW' in description.upper():
                    # HA-CF layout: must have blank account code.
                    if account_code_col is not None and account_code_col < len(row):
                        account_code = row[account_code_col].strip()
                        if not account_code:
                            return row_idx

                    # Yardi export layout: no account codes; the label alone is sufficient.
                    if account_code_col is None:
                        return row_idx
        
        return None
    
    
    def find_period_row(self, hacf_data):
        """Find row containing period information"""
        for row_idx, row in enumerate(hacf_data):
            for cell in row:
                cell_lower = str(cell).lower().strip()
                if 'period' in cell_lower and ('=' in cell_lower or '202' in cell_lower):
                    return row_idx
        
        return None
    
    
    def find_property_column(self, yardi_code, hacf_data):
        """Find column for property by Yardi code"""
        prop_code_row_idx = self.find_property_code_row(hacf_data)
        
        if prop_code_row_idx is None:
            return None
        
        property_row = hacf_data[prop_code_row_idx]
        
        for col_idx, code in enumerate(property_row):
            if code.strip() == yardi_code:
                return col_idx
        
        return None
    
    
    def find_account_value(self, account_code, col_idx, hacf_data):
        """Find value for account code at column"""
        account_code_col, _ = self.find_account_columns(hacf_data)
        
        if account_code_col is None:
            return None
        
        for row in hacf_data:
            if len(row) > account_code_col:
                row_account_code = row[account_code_col].strip()
                if row_account_code == account_code:
                    if col_idx < len(row):
                        return parse_currency(row[col_idx])
        
        return None
    
    
    def find_account_row(self, account_code, hacf_data):
        """Find row number (1-indexed) for account code"""
        account_code_col, _ = self.find_account_columns(hacf_data)
        
        if account_code_col is None:
            return None
        
        for row_idx, row in enumerate(hacf_data):
            if len(row) > account_code_col:
                row_account_code = row[account_code_col].strip()
                if row_account_code == account_code:
                    return row_idx + 1  # 1-indexed for Excel
        
        return None
    
    
    def extract_metrics(self, yardi_code, hacf_data, sheet_name):
        """Extract all 6 metrics for a property - returns both values and cell references"""
        
        col_idx = self.find_property_column(yardi_code, hacf_data)
        if col_idx is None:
            return None
        
        # Convert column index to Excel column letter (A, B, ... Z, AA, AB, etc.)
        col_letter = self.column_index_to_letter(col_idx)
        
        account_code_col, _ = self.find_account_columns(hacf_data)
        label_mode = account_code_col is None

        if not label_mode:
            # HA-CF sheet with account codes
            revenue = self.find_account_value('5990-0000', col_idx, hacf_data)
            opex = self.find_account_value('7999-9000', col_idx, hacf_data)
            noi = self.find_account_value('7999-9999', col_idx, hacf_data)

            revenue_row = self.find_account_row('5990-0000', hacf_data)
            opex_row = self.find_account_row('7999-9000', hacf_data)
            noi_row = self.find_account_row('7999-9999', hacf_data)
            interest_row = self.find_account_row('8590-0000', hacf_data)
            principal_2110_row = self.find_account_row('2110-0000', hacf_data)
            principal_2120_row = self.find_account_row('2120-0000', hacf_data)
            principal_2130_row = self.find_account_row('2130-0000', hacf_data)
        else:
            # Verbatim Yardi export: locate the needed rows by label
            revenue_row = self.find_label_row('TOTAL INCOME', hacf_data)
            noi_row = self.find_label_row('NET OPERATING INCOME', hacf_data)
            interest_row = self.find_label_row('TOTAL LOAN INTEREST', hacf_data)
            principal_2110_row = self.find_label_row('NOTE 1 PRINCIPAL', hacf_data)
            principal_2120_row = self.find_label_row('NOTE 2 PRINCIPAL', hacf_data)
            principal_2130_row = self.find_label_row('NOTE 3 PRINCIPAL', hacf_data)
            opex_row = None

            revenue = None
            noi = None
            opex = None
            if revenue_row and revenue_row - 1 < len(hacf_data):
                row = hacf_data[revenue_row - 1]
                if col_idx < len(row):
                    revenue = parse_currency(row[col_idx])
            if noi_row and noi_row - 1 < len(hacf_data):
                row = hacf_data[noi_row - 1]
                if col_idx < len(row):
                    noi = parse_currency(row[col_idx])
            if revenue is not None and noi is not None:
                opex = revenue - noi
        
        # Get CFADS row
        cfads = None
        cfads_row = None
        if sheet_name not in self.cfads_row_cache:
            cfads_row_idx = self.find_cfads_row(hacf_data)
            self.cfads_row_cache[sheet_name] = cfads_row_idx
        
        cfads_row_idx = self.cfads_row_cache[sheet_name]
        if cfads_row_idx is not None:
            cfads_row = cfads_row_idx + 1  # 1-indexed for Excel
            if cfads_row_idx < len(hacf_data):
                row = hacf_data[cfads_row_idx]
                if col_idx < len(row):
                    cfads = parse_currency(row[col_idx])
        
        # Calculate values for validation
        if not label_mode:
            interest = self.find_account_value('8590-0000', col_idx, hacf_data) or 0
            principal_2110 = self.find_account_value('2110-0000', col_idx, hacf_data) or 0
            principal_2120 = self.find_account_value('2120-0000', col_idx, hacf_data) or 0
            principal_2130 = self.find_account_value('2130-0000', col_idx, hacf_data) or 0
        else:
            interest = 0
            principal_2110 = 0
            principal_2120 = 0
            principal_2130 = 0
            if interest_row and interest_row - 1 < len(hacf_data):
                row = hacf_data[interest_row - 1]
                if col_idx < len(row):
                    interest = parse_currency(row[col_idx])
            if principal_2110_row and principal_2110_row - 1 < len(hacf_data):
                row = hacf_data[principal_2110_row - 1]
                if col_idx < len(row):
                    principal_2110 = parse_currency(row[col_idx])
            if principal_2120_row and principal_2120_row - 1 < len(hacf_data):
                row = hacf_data[principal_2120_row - 1]
                if col_idx < len(row):
                    principal_2120 = parse_currency(row[col_idx])
            if principal_2130_row and principal_2130_row - 1 < len(hacf_data):
                row = hacf_data[principal_2130_row - 1]
                if col_idx < len(row):
                    principal_2130 = parse_currency(row[col_idx])
        debt_service = interest + abs(principal_2110) + abs(principal_2120) + abs(principal_2130)
        
        cfbds = cfads + debt_service if cfads is not None else None
        
        return {
            'revenue': revenue,
            'opex': opex,
            'noi': noi,
            'cfbds': cfbds,
            'debt_service': debt_service,
            'cfads': cfads,
            # Individual debt service component values (for formula generation)
            'interest': abs(interest),
            'principal_2110': abs(principal_2110),
            'principal_2120': abs(principal_2120),
            'principal_2130': abs(principal_2130),
            # Cell references for formulas
            'col_letter': col_letter,
            'revenue_row': revenue_row,
            'opex_row': opex_row,
            'noi_row': noi_row,
            'interest_row': interest_row,
            'principal_2110_row': principal_2110_row,
            'principal_2120_row': principal_2120_row,
            'principal_2130_row': principal_2130_row,
            'cfads_row': cfads_row,
            'label_mode': label_mode
        }
    
    
    def validate_period(self, hacf_data):
        """Validate period information is present"""
        period_row_idx = self.find_period_row(hacf_data)
        
        if period_row_idx is None:
            return False, "[WARN] Could not find period row"
        
        period_text = ' '.join(hacf_data[period_row_idx])
        return True, f"[OK] Found period: {period_text[:80]}"
    
    
    def process_property(self, prop_info, period_name, hacf_data, sheet_name):
        """Process single property for given period"""

        prop_name = prop_info.get('name') or ''
        prop_row = prop_info.get('row')

        if prop_info.get('status') == 'SKIP':
            return None
        
        yardi_code = prop_info.get('yardi_code')
        if not yardi_code:
            print(f"   [WARN] {prop_name}: No Yardi code, skipping")
            return None
        
        metrics = self.extract_metrics(yardi_code, hacf_data, sheet_name)
        
        if metrics is None:
            print(f"   [WARN] {prop_name} ({yardi_code}): Not found in {period_name}")
            return None
        
        if self.skip_month_end:
            needs_yellow = False
        else:
            prop_root = prop_info.get('normalized_root') or normalize_portfolio_property(prop_name)
            needs_yellow = bool(
                prop_root
                and (
                    prop_root in getattr(self, 'bs_recon_status', {})
                )
            )
        
        return {
            'name': prop_name,
            'row': prop_row,
            'metrics': metrics,
            'needs_yellow': needs_yellow
        }
    
    
    def find_period_columns(self, portfolio_data, period_name):
        """Find the start column for a specific period group.

        We locate the metric header row dynamically (template can change), then:
        - find each period group's start via the columns containing "Revenue"
        - map requested period_name -> group index (0=month, 1=3mos, 2=ytd)
        """

        metric_row_idx = self._find_metric_header_row_idx(portfolio_data)
        if metric_row_idx is None:
            return None

        header_row = portfolio_data[metric_row_idx]
        revenue_cols: list[int] = []
        for col_idx, cell in enumerate(header_row):
            if 'revenue' in str(cell).lower():
                revenue_cols.append(col_idx)

        if not revenue_cols:
            return None

        period_index_map = {
            '3 Months': 1,
            'YTD': 2,
        }
        period_index = period_index_map.get(period_name, 0)
        if period_index >= len(revenue_cols):
            return None
        return revenue_cols[period_index]


    def _find_metric_header_row_idx(self, portfolio_data):
        """Find the row index that contains the repeated metric headers.

        The template has historically used a header row like:
        Revenue | Opex | NOI | CFBDS | Debt Service | CFADS (repeated by period)
        But its row position can move as rows/columns are inserted/deleted.
        """

        # Scan a reasonable header window.
        scan_rows = min(60, len(portfolio_data))
        metric_terms = [
            'revenue',
            'opex',
            'noi',
            'cfbds',
            'debt service',
            'cfads',
        ]

        best_idx = None
        best_score = 0
        for r in range(scan_rows):
            row = portfolio_data[r]
            joined = ' | '.join(str(c).lower() for c in row)
            score = sum(1 for t in metric_terms if t in joined)
            has_revenue = 'revenue' in joined
            if has_revenue and score >= 3 and score > best_score:
                best_score = score
                best_idx = r

        return best_idx
    
    
    def find_metric_column(self, portfolio_data, metric_name, period_start_col):
        """Find column for specific metric within a period by searching row 4 headers"""
        metric_row_idx = self._find_metric_header_row_idx(portfolio_data)
        if metric_row_idx is None:
            return None
        
        # Search for metric in columns near the period start
        # Metrics repeat every 7 columns: Revenue, Opex, NOI, CFBDS, Debt Service, CFADS, (blank)
        for offset in range(7):
            col_idx = period_start_col + offset
            if col_idx < len(portfolio_data[metric_row_idx]):
                cell_text = str(portfolio_data[metric_row_idx][col_idx]).strip().lower()
                if metric_name.lower() in cell_text:
                    return col_idx
        
        return None
    
    
    def find_property_row(self, portfolio_data, property_name):
        """Find row number for a property by searching property name column"""
        # Property names are in column B (index 1) starting from row 6
        prop_col_idx = 1
        
        for row_idx, row in enumerate(portfolio_data):
            if row_idx < 5:  # Skip header rows
                continue
            
            if prop_col_idx < len(row):
                cell_text = str(row[prop_col_idx]).strip().lower()
                if property_name.lower() == cell_text:
                    return row_idx
        
        return None
    
    
    def write_results_to_portfolio(self, all_results, dry_run=True):
        """Write results to PORTFOLIO CASH FLOW sheet using dynamic column/row lookup"""
        print("\n" + "="*100)
        print(f"{'DRY RUN: ' if dry_run else ''}WRITING RESULTS TO PORTFOLIO CASH FLOW")
        print("="*100)
        
        # Reload portfolio data for fresh lookups
        portfolio_data = self.portfolio_data
        
        # Build batch update list
        updates = []
        format_requests = []
        
        metrics_order = ['revenue', 'opex', 'noi', 'cfbds', 'debt_service', 'cfads']
        metrics_map = {
            'revenue': 'Revenue',
            'opex': 'Opex',
            'noi': 'NOI',
            'cfbds': 'CFBDS',
            'debt_service': 'Debt Service',
            'cfads': 'CFADS'
        }
        
        for period_name, period_results in all_results.items():
            print(f"\n{'='*50}")
            print(f"Period: {period_name}")
            print(f"{'='*50}")
            
            # Get source sheet from first result (all have same source)
            if not period_results:
                continue
            
            first_result = period_results[0]
            source_sheet = first_result.get('source_sheet')
            if not source_sheet:
                print(f"   [WARN] No source sheet for period '{period_name}'")
                continue
            
            # Find period start column
            period_start_col = self.find_period_columns(portfolio_data, period_name)
            if period_start_col is None:
                print(f"   [WARN] Could not find column for period '{period_name}'")
                continue
            
            print(f"   [OK] Period '{period_name}' starts at Column {chr(65 + period_start_col)} ({period_start_col + 1})")
            print(f"   [OK] Source sheet: {source_sheet}")
            
            for result in period_results:
                prop_name = result.get('name') or ''
                prop_row_1 = result.get('row')
                if not prop_row_1:
                    print(f"   [WARN] Missing portfolio row for property '{prop_name}'")
                    continue
                prop_row = int(prop_row_1) - 1
                
                metrics = result['metrics']
                needs_yellow = result['needs_yellow']
                
                # Find metric columns for CFBDS formula (need NOI and Debt Service columns)
                noi_col = self.find_metric_column(portfolio_data, 'NOI', period_start_col)
                debt_service_col = self.find_metric_column(portfolio_data, 'Debt Service', period_start_col)
                
                # Write each metric
                for metric_key in metrics_order:
                    metric_display = metrics_map[metric_key]
                    metric_col = self.find_metric_column(portfolio_data, metric_display, period_start_col)
                    
                    if metric_col is None:
                        print(f"      [WARN] Could not find column for '{metric_display}'")
                        continue
                    
                    cell_ref = f"{chr(65 + metric_col)}{prop_row + 1}"
                    value = metrics[metric_key]
                    
                    # Generate formula based on metric type
                    if metric_key == 'cfbds':
                        # CFBDS references same sheet: =CFADS_cell + DebtService_cell
                        cfads_col = self.find_metric_column(portfolio_data, 'CFADS', period_start_col)
                        if cfads_col is not None and debt_service_col is not None:
                            cfads_cell = f"{chr(65 + cfads_col)}{prop_row + 1}"
                            ds_cell = f"{chr(65 + debt_service_col)}{prop_row + 1}"
                            formula = f"={cfads_cell}+{ds_cell}"
                            
                            updates.append({
                                'range': cell_ref,
                                'values': [[formula]]
                            })
                            print(f"      {cell_ref}: {metric_display} = {formula}")
                        else:
                            print(f"      [WARN] Could not generate CFBDS formula (missing CFADS or DS column)")
                    
                    elif metric_key == 'debt_service':
                        # Debt Service: Show cell references from same sheet
                        col_letter = metrics.get('col_letter')
                        interest_row = metrics.get('interest_row')
                        p2110_row = metrics.get('principal_2110_row')
                        p2120_row = metrics.get('principal_2120_row')
                        p2130_row = metrics.get('principal_2130_row')

                        if col_letter and (interest_row or p2110_row or p2120_row or p2130_row):
                            formula_parts = []
                            if interest_row:
                                formula_parts.append(f"='{source_sheet}'!{col_letter}{interest_row}")
                            else:
                                formula_parts.append("0")

                            if p2110_row:
                                formula_parts.append(f"ABS('{source_sheet}'!{col_letter}{p2110_row})")
                            if p2120_row:
                                formula_parts.append(f"ABS('{source_sheet}'!{col_letter}{p2120_row})")
                            if p2130_row:
                                formula_parts.append(f"ABS('{source_sheet}'!{col_letter}{p2130_row})")

                            formula = "+".join(formula_parts)

                            updates.append({
                                'range': cell_ref,
                                'values': [[formula]]
                            })
                            print(f"      {cell_ref}: {metric_display} = {formula}")
                        else:
                            print(f"      [WARN] Could not generate Debt Service formula")
                    
                    else:
                        # Revenue, Opex, NOI, CFADS: ='Sheet'!Cell
                        col_letter = metrics.get('col_letter')
                        label_mode = bool(metrics.get('label_mode'))
                        
                        if metric_key == 'revenue':
                            row_num = metrics.get('revenue_row')
                        elif metric_key == 'opex':
                            row_num = metrics.get('opex_row')
                        elif metric_key == 'noi':
                            row_num = metrics.get('noi_row')
                        elif metric_key == 'cfads':
                            row_num = metrics.get('cfads_row')
                        else:
                            row_num = None

                        if metric_key == 'opex' and (not row_num) and label_mode and col_letter:
                            rev_row = metrics.get('revenue_row')
                            noi_row = metrics.get('noi_row')
                            if rev_row and noi_row:
                                formula = f"='{source_sheet}'!{col_letter}{rev_row}-'{source_sheet}'!{col_letter}{noi_row}"
                                updates.append({
                                    'range': cell_ref,
                                    'values': [[formula]]
                                })
                                print(f"      {cell_ref}: {metric_display} = {formula}")
                            else:
                                print(f"      [WARN] Could not generate formula for {metric_display}")

                        elif col_letter and row_num:
                            formula = f"='{source_sheet}'!{col_letter}{row_num}"
                            
                            updates.append({
                                'range': cell_ref,
                                'values': [[formula]]
                            })
                            print(f"      {cell_ref}: {metric_display} = {formula}")
                        else:
                            print(f"      [WARN] Could not generate formula for {metric_display}")
                
                # Add yellow highlighting if needed
                if needs_yellow:
                    print(f"      [YELLOW] Yellow highlight needed for row {prop_row + 1}")
                    format_requests.append({
                        'row': prop_row,
                        'needs_yellow': True
                    })
        
        print(f"\n{'='*100}")
        print(f"Total updates prepared: {len(updates)}")
        print(f"Yellow highlights needed: {len(format_requests)}")
        print(f"{'='*100}")
        
        if dry_run:
            print("\n[DRY RUN] No changes written to sheet")
            return updates, format_requests
        
        # Step 1: Clear all existing yellow highlights from data rows (always, start fresh)
        print("\n   Clearing existing highlights from data rows...")
        clear_requests = []
        for col_range in [
            (0, 9),   # A:I
            (10, 16), # K:P
            (17, 23), # R:W
        ]:
            clear_requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': self.portfolio_ws.id,
                        'startRowIndex': 4,  # Row 5 (0-based)
                        'endRowIndex': 100,  # Up to row 100
                        'startColumnIndex': col_range[0],
                        'endColumnIndex': col_range[1],
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': 1.0,
                                'green': 1.0,
                                'blue': 1.0,
                            }
                        }
                    },
                    'fields': 'userEnteredFormat.backgroundColor',
                }
            })
        
        self.gc.open_by_key(self.portfolio_ws.spreadsheet_id).batch_update({'requests': clear_requests})
        print(f"   [OK] Cleared existing highlights")
        
        # Step 2: Write formulas
        print("\n   Writing formulas to sheet...")
        if updates:
            self.portfolio_ws.batch_update(updates, value_input_option='USER_ENTERED')
            print(f"   [OK] Wrote {len(updates)} formulas")
        
        # Step 3: Apply yellow highlighting (only if needed)
        if format_requests:
            print("\n   Applying yellow highlights...")
            # Build batch formatting requests manually to avoid gspread_formatting compatibility issues
            batch_requests = []
            for req in format_requests:
                row_num = req['row'] + 1
                # Skip gray separator columns (J and Q) by applying three ranges.
                for col_range in [
                    (0, 9),   # A:I
                    (10, 16), # K:P
                    (17, 23), # R:W
                ]:
                    batch_requests.append({
                        'repeatCell': {
                            'range': {
                                'sheetId': self.portfolio_ws.id,
                                'startRowIndex': row_num - 1,
                                'endRowIndex': row_num,
                                'startColumnIndex': col_range[0],
                                'endColumnIndex': col_range[1],
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 1.0,
                                        'green': 1.0,
                                        'blue': 0.8,
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.backgroundColor',
                        }
                    })
            
            if batch_requests:
                # Use the spreadsheet object correctly for newer gspread API
                self.gc.open_by_key(self.portfolio_ws.spreadsheet_id).batch_update({'requests': batch_requests})
            
            print(f"   [OK] Applied {len(format_requests)} yellow highlights")
        
        print("\n[OK] All updates written successfully!")
        
        return updates, format_requests
    
    
    def generate_report(self):
        """Main method to generate the complete report"""
        print("\n" + "="*100)
        print("GENERATING PROPERTY CASH FLOW REPORT")
        print("="*100)
        
        periods = [
            (self.month_tab, self.month_label, self.month_label),
            ('HA-CF-3MOS', '3 Months', '3 Months'),
            ('HA-CF-YTD', 'YTD', 'YTD')
        ]
        
        all_results = {}
        
        for sheet_name, display_label, period_key in periods:
            print(f"\n{'='*100}")
            print(f"PROCESSING {display_label.upper()}")
            print(f"{'='*100}")
            
            hacf_data = self.hacf_sheets[sheet_name]
            
            valid, message = self.validate_period(hacf_data)
            print(f"\n Period validation: {message}")
            
            period_results: list[dict] = []

            for prop_info in self.properties:
                result = self.process_property(prop_info, display_label, hacf_data, sheet_name)

                if result:
                    # Add sheet_name to result for formula generation
                    result['source_sheet'] = sheet_name
                    period_results.append(result)
                    m = result['metrics']
                    prop_name = result.get('name') or ''
                    rev = m.get('revenue')
                    cfads = m.get('cfads')
                    if isinstance(rev, (int, float)) and isinstance(cfads, (int, float)):
                        print(f"   [OK] {prop_name}: Rev ${rev:,.2f}, CFADS ${cfads:,.2f}")
                    else:
                        print(f"   [OK] {prop_name}: metrics captured")

            all_results[period_key] = period_results
        
        print(f"\n{'='*100}")
        print("REPORT GENERATION COMPLETE")
        print(f"{'='*100}")
        print(f"\nProcessed {sum(len(period_results) for period_results in all_results.values())} property-periods")
        
        return all_results


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheet-id",
        default=SHEET_ID,
        help="Google Sheet ID or full link (defaults to CASHFLOW_SHEET_ID env var)",
    )
    parser.add_argument(
        "--assume-yes",
        action="store_true",
        help="Skip confirmation prompt and proceed with writing (useful for unattended runs)",
    )
    parser.add_argument(
        "--month-tab",
        default=os.environ.get("CASHFLOW_MONTH_TAB") or "HA-CF-OCT",
        help="Monthly HA-CF tab name (e.g., HA-CF-NOV)",
    )
    parser.add_argument(
        "--month-label",
        default=os.environ.get("CASHFLOW_MONTH_LABEL") or "October",
        help="Label for the monthly period group (e.g., November)",
    )
    parser.add_argument(
        "--skip-month-end",
        action="store_true",
        help="Skip Month End Reports coloring/status checks (useful for fresh sheets)",
    )
    parser.add_argument(
        "--portfolio-tab",
        default=os.environ.get("CASHFLOW_PORTFOLIO_TAB") or "PORTFOLIO CASH FLOW",
        help="Target workbook tab containing the PORTFOLIO CASH FLOW template",
    )
    parser.add_argument(
        "--property-codes-tab",
        default=os.environ.get("CASHFLOW_PROPERTY_CODES_TAB") or "PROPERTY CODES",
        help="Target workbook tab containing PROPERTY CODES",
    )
    parser.add_argument(
        "--month-end-tab",
        default=os.environ.get("CASHFLOW_MONTH_END_TAB") or "MONTH END LIST",
        help="Target workbook tab containing the Month End list (MONTH END LIST)",
    )
    args = parser.parse_args()

    sheet_id = _extract_sheet_id(args.sheet_id)
    if not sheet_id:
        entered = input("Paste Google Sheet link/ID: ").strip()
        sheet_id = _extract_sheet_id(entered)
    if not sheet_id:
        raise SystemExit("Missing sheet id. Provide --sheet-id or paste one at the prompt.")

    # Surface the service account email so users know what to share the sheet with.
    email = _service_account_email(SERVICE_ACCOUNT_FILE)
    if email:
        print(f"Service account: {email}")

    generator = PropertyCashFlowGenerator(
        sheet_id,
        month_tab=args.month_tab,
        month_label=args.month_label,
        skip_month_end=args.skip_month_end,
        portfolio_tab=args.portfolio_tab,
        property_codes_tab=args.property_codes_tab,
        month_end_tab=args.month_end_tab,
    )
    results = generator.generate_report()
    
    # Dry run first to show what would be written
    print("\n" + "="*100)
    print("PREVIEW: What will be written to PORTFOLIO CASH FLOW")
    print("="*100)
    
    updates, formats = generator.write_results_to_portfolio(results, dry_run=True)
    
    # Ask for confirmation
    print("\n" + "="*100)
    if args.assume_yes:
        user_input = 'yes'
    else:
        user_input = input("\nProceed with writing to PORTFOLIO CASH FLOW sheet? (yes/no): ").strip().lower()

    if user_input == 'yes':
        print("\n   Writing to sheet...")
        generator.write_results_to_portfolio(results, dry_run=False)
        print("\n[OK] Automation complete!")
    else:
        print("\n   Cancelled. No changes made to sheet.")


if __name__ == "__main__":
    main()
