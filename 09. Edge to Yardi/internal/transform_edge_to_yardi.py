"""Transform Edge GL CSV files to Yardi import format.

Phase 2 of the Edge-to-Yardi workflow.

This script:
1. Reads downloaded Edge GL CSVs from edge_downloads/
2. Transforms each file:
   - Column I: Populated with property_code from filename
   - Column K: Validated/corrected account codes
3. Saves transformed files to import_template/
4. Generates compiled CSVs for all facilities and Jay-only facilities
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============================================================================
# CONSTANTS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FACILITY_ORDER_PATH = PROJECT_ROOT.parent / ".helper_artifacts" / "09. Edge to Yardi" / "facility_order" / "facility_order.json"

# Valid account code pattern: NNNN-NNNN (4 digits, dash, 4 digits)
VALID_ACCOUNT_CODE_PATTERN = re.compile(r"^\d{4}-\d{4}$")

# Column indices (0-based)
COL_PROPERTY_CODE = 8   # Column I
COL_AMOUNT = 9          # Column J
COL_ACCOUNT_CODE = 10   # Column K
COL_DESCRIPTION = 14    # Column O

DEBUG = False


def debug_print(msg: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {msg}")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CashCodeCorrection:
    property_code: str
    date: str
    original_code: str
    corrected_code: str
    description: str
    amount: str


@dataclass
class TransformResult:
    property_code: str
    input_file: str
    output_file: str
    row_count: int
    codes_fixed: int
    cash_codes_fixed: int = 0
    unmapped_descriptions: list[str] = field(default_factory=list)
    status: str = "success"
    error_message: Optional[str] = None


@dataclass
class TransformReport:
    report_month: str
    started_at: str
    ended_at: Optional[str] = None
    status: str = "IN_PROGRESS"
    total_files: int = 0
    success_count: int = 0
    error_count: int = 0
    total_rows: int = 0
    total_codes_fixed: int = 0
    total_cash_codes_fixed: int = 0
    compiled_file: Optional[str] = None
    jay_file: Optional[str] = None
    jay_property_files: list[str] = field(default_factory=list)
    cash_corrections_file: Optional[str] = None
    results: list[TransformResult] = field(default_factory=list)
    all_unmapped_descriptions: list[str] = field(default_factory=list)
    all_cash_corrections: list[CashCodeCorrection] = field(default_factory=list)


# ============================================================================
# ACCOUNT CODE MAPPING
# ============================================================================

def load_account_code_corrections(corrections_path: Path) -> dict[str, str]:
    """Load account code corrections from CSV.
    
    Maps Incorrect Code -> Correct Code
    This handles Edge data quality issues where wrong/truncated codes appear.
    """
    if not corrections_path.exists():
        debug_print(f"Account code corrections not found: {corrections_path}")
        return {}
    
    corrections: dict[str, str] = {}
    with corrections_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            incorrect = (row.get("Incorrect Code") or "").strip()
            correct = (row.get("Correct Code") or "").strip()
            if incorrect and correct:
                corrections[incorrect] = correct
    
    debug_print(f"Loaded {len(corrections)} account code corrections")
    return corrections


def load_account_code_mapping(mapping_path: Path) -> dict[str, str]:
    """Load account code mapping from CSV.
    
    Maps Description -> Yardi Code
    """
    if not mapping_path.exists():
        print(f"  [WARN] Account code mapping not found: {mapping_path}")
        return {}
    
    mapping: dict[str, str] = {}
    with mapping_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            description = (row.get("Description") or "").strip()
            yardi_code = (row.get("Yardi Code") or "").strip()
            if description and yardi_code:
                mapping[description] = yardi_code
    
    debug_print(f"Loaded {len(mapping)} account code mappings")
    return mapping


def load_cash_account_mappings(json_path: Path) -> dict[str, dict[str, str]]:
    """Load property-specific cash account codes from JSON.
    
    Maps property_code -> {description: yardi_code}
    This allows different cash types (ACH, Credit Card, etc.) to have different accounts.
    
    Source: Google Sheet fetched by fetch_cash_account_mappings.py
    
    Expected JSON format:
    {
        "ephss": {
            "Cash": "1110-4329",
            "Credit Card - Visa": "1110-4977",
            ...
        },
        ...
    }
    """
    if not json_path.exists():
        debug_print(f"Cash account mappings not found: {json_path}")
        return {}
    
    with json_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)
    debug_print(f"Loaded {len(mapping)} property cash account mappings")
    return mapping


def is_valid_account_code(code: str) -> bool:
    """Check if account code matches NNNN-NNNN format."""
    if not code:
        return False
    return bool(VALID_ACCOUNT_CODE_PATTERN.match(code.strip()))


def is_cash_description(description: str) -> bool:
    """Check if description indicates a cash/payment transaction."""
    desc_lower = description.lower()
    cash_keywords = [
        "cash",
        "checks",
        "ach",
        "money order",
        "credit card",
        "refund checks",
    ]
    return any(keyword in desc_lower for keyword in cash_keywords)


# ============================================================================
# FACILITY ASSIGNEE MAPPING
# ============================================================================

def load_facility_assignees() -> dict[str, str]:
    """Load property_code -> assignee mapping from facility_order.json."""
    if not FACILITY_ORDER_PATH.exists():
        print(f"  [WARN] Facility order not found: {FACILITY_ORDER_PATH}")
        return {}
    
    with FACILITY_ORDER_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    assignees: dict[str, str] = {}
    for row in data.get("rows", []):
        prop_code = row.get("property_code", "").strip().lower()
        assignee = row.get("assignee", "").strip()
        if prop_code:
            assignees[prop_code] = assignee
    
    debug_print(f"Loaded {len(assignees)} facility assignees")
    return assignees


# ============================================================================
# CASH ACCOUNT CORRECTION (FINAL STEP)
# ============================================================================

def _normalize_cash_description(description: str) -> str:
    """Normalize cash description for lookup in mapping.
    
    Handles variations like 'Credit Card - Mastercard' vs 'Credit Card - Master Card'.
    """
    desc = description.strip()
    desc_lower = desc.lower()
    
    # Normalize MasterCard variations
    if "mastercard" in desc_lower or "master card" in desc_lower:
        return "Credit Card - Master Card"
    
    # Normalize other credit card types
    if "credit card" in desc_lower:
        if "visa" in desc_lower:
            return "Credit Card - Visa"
        if "discover" in desc_lower:
            return "Credit Card - Discover"
        if "american express" in desc_lower or "amex" in desc_lower:
            return "Credit Card - American Express"
        if "other" in desc_lower:
            return "Credit Card - Other"
    
    # Normalize other cash types
    if desc_lower == "cash":
        return "Cash"
    if desc_lower == "checks":
        return "Checks"
    if desc_lower == "ach":
        return "ACH"
    if desc_lower == "money order":
        return "Money Order"
    if "refund check" in desc_lower:
        return "Refund Checks"
    
    # Return as-is if no normalization needed
    return desc


def apply_cash_account_corrections(
    csv_path: Path,
    property_code: str,
    cash_description_mapping: dict[str, str],
) -> list[CashCodeCorrection]:
    """Apply property-specific cash account code corrections based on description.
    
    This is the FINAL transformation step that fixes incorrect cash account codes
    that appear in Edge exports. Modifies the CSV file in place.
    
    Args:
        csv_path: Path to the CSV file to modify
        property_code: The property code (for logging)
        cash_description_mapping: Dict mapping description -> correct yardi code
    
    Returns list of corrections made.
    """
    corrections: list[CashCodeCorrection] = []
    
    # Read CSV
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    # Apply corrections
    for row in rows:
        if len(row) <= COL_ACCOUNT_CODE:
            continue
        
        current_code = row[COL_ACCOUNT_CODE].strip()
        description = row[COL_DESCRIPTION].strip() if len(row) > COL_DESCRIPTION else ""
        
        # Skip if not a cash transaction or doesn't start with 11
        if not is_cash_description(description) or not current_code.startswith("11"):
            continue
        
        # Normalize description and look up the correct code
        normalized_desc = _normalize_cash_description(description)
        correct_code = cash_description_mapping.get(normalized_desc)
        
        if not correct_code:
            debug_print(f"No mapping found for description: {description} (normalized: {normalized_desc})")
            continue
        
        # Only correct if the current code is different
        if current_code != correct_code:
            # Extract transaction date (column E, index 4)
            date_str = row[4] if len(row) > 4 else ""
            amount = row[COL_AMOUNT] if len(row) > COL_AMOUNT else ""
            
            corrections.append(CashCodeCorrection(
                property_code=property_code,
                date=date_str,
                original_code=current_code,
                corrected_code=correct_code,
                description=description,
                amount=amount,
            ))
            
            # Apply correction
            row[COL_ACCOUNT_CODE] = correct_code
            debug_print(f"Cash correction: {current_code} -> {correct_code} for {description}")
    
    # Write corrected CSV
    if corrections:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    
    return corrections


# ============================================================================
# CSV TRANSFORMATION
# ============================================================================

def extract_property_code_from_filename(filename: str) -> Optional[str]:
    """Extract property_code from filename.
    
    e.g., "edge_gl_by_day__cpwest__2025-12.csv" -> "cpwest"
    """
    match = re.match(r"edge_gl_by_day__([^_]+)__", filename)
    if match:
        return match.group(1)
    return None


def transform_csv_file(
    input_path: Path,
    output_path: Path,
    property_code: str,
    account_mapping: dict[str, str],
    account_corrections: dict[str, str],
) -> TransformResult:
    """Transform a single Edge GL CSV file.
    
    - Column I: Set to property_code
    - Column K: Validate/fix account codes
    """
    result = TransformResult(
        property_code=property_code,
        input_file=str(input_path),
        output_file=str(output_path),
        row_count=0,
        codes_fixed=0,
    )
    
    try:
        # Read input CSV
        with input_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        if not rows:
            result.status = "error"
            result.error_message = "Empty CSV file"
            return result
        
        transformed_rows: list[list[str]] = []
        unmapped_set: set[str] = set()
        
        for row in rows:
            # Ensure row has enough columns
            while len(row) <= COL_DESCRIPTION:
                row.append("")
            
            # Column I: Set property code
            row[COL_PROPERTY_CODE] = property_code
            
            # Column K: Validate/fix account code
            current_code = row[COL_ACCOUNT_CODE].strip()
            
            # STEP 1: Check if code needs correction (wrong/truncated codes from Edge)
            if current_code in account_corrections:
                row[COL_ACCOUNT_CODE] = account_corrections[current_code]
                result.codes_fixed += 1
                debug_print(f"Corrected code '{current_code}' -> '{account_corrections[current_code]}'")
            elif is_valid_account_code(current_code):
                # Code is valid, keep it
                pass
            else:
                # Code is invalid/blank, try to map from description
                description = row[COL_DESCRIPTION].strip() if len(row) > COL_DESCRIPTION else ""
                mapped_code = account_mapping.get(description, "")
                
                if mapped_code:
                    row[COL_ACCOUNT_CODE] = mapped_code
                    result.codes_fixed += 1
                    debug_print(f"Mapped '{description}' -> '{mapped_code}'")
                else:
                    # Leave as-is but track unmapped
                    if description:
                        unmapped_set.add(description)
            
            transformed_rows.append(row)
            result.row_count += 1
        
        result.unmapped_descriptions = sorted(unmapped_set)
        
        # Write output CSV
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(transformed_rows)
        
        result.status = "success"
        
    except Exception as e:
        result.status = "error"
        result.error_message = str(e)
    
    return result


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def run_transform_workflow(
    month_folder: str,
    property_filter: Optional[list[str]] = None,
    skip_compile: bool = False,
) -> TransformReport:
    """Run the full transformation workflow.
    
    Args:
        month_folder: Month folder name (e.g., '12. Dec')
        property_filter: Optional list of property codes to process. If None, process all.
        skip_compile: If True, skip regenerating compiled files (useful for single property updates)
    """
    
    # Parse report month from folder name and infer year from source files
    month_match = re.match(r"(\d+)\.", month_folder)
    month_num = month_match.group(1) if month_match else "00"
    
    # Try to extract year from source filenames (e.g., "edge_gl_by_day__cpwest__2025-12.csv")
    month_dir = PROJECT_ROOT / month_folder
    edge_downloads_dir = month_dir / "Output" / "edge_downloads"
    source_files = list(edge_downloads_dir.glob("edge_gl_by_day__*__*.csv"))
    
    year = None
    if source_files:
        # Extract year from first source file
        filename_match = re.search(r"(\d{4})-\d{2}\.csv$", source_files[0].name)
        if filename_match:
            year = filename_match.group(1)
    
    if not year:
        # Fallback: use current year
        from datetime import date
        year = str(date.today().year)
    
    report_month = f"{year}-{month_num.zfill(2)}"
    
    report = TransformReport(
        report_month=report_month,
        started_at=datetime.now().isoformat(),
    )
    
    # Set up paths (already defined above for year extraction)
    import_template_dir = month_dir / "Output" / "import_template"
    output_dir = month_dir / "Output"
    
    # Load mappings
    print("\n=== Loading mappings ===")
    account_mapping_path = month_dir / "Input" / "account code mapping.csv"
    account_mapping = load_account_code_mapping(account_mapping_path)
    print(f"Loaded {len(account_mapping)} account code mappings")
    
    account_corrections_path = month_dir / "Input" / "account_code_corrections.csv"
    account_corrections = load_account_code_corrections(account_corrections_path)
    if account_corrections:
        print(f"Loaded {len(account_corrections)} account code corrections")
    
    # Load property-specific cash account mapping (from Google Sheet)
    cash_mapping_path = month_dir / "Input" / "cash_account_mappings.json"
    cash_account_mapping = load_cash_account_mappings(cash_mapping_path)
    if cash_account_mapping:
        print(f"Loaded {len(cash_account_mapping)} property cash account mappings")
    
    facility_assignees = load_facility_assignees()
    jay_facilities = {k for k, v in facility_assignees.items() if v.lower() == "jay"}
    print(f"Found {len(jay_facilities)} facilities assigned to Jay")
    
    # Find source files
    print("\n=== Finding source files ===")
    source_files = sorted(edge_downloads_dir.glob("edge_gl_by_day__*__*.csv"))
    
    # Filter by property if specified
    if property_filter:
        property_filter_lower = [p.lower() for p in property_filter]
        source_files = [
            f for f in source_files
            if extract_property_code_from_filename(f.name) and
               extract_property_code_from_filename(f.name).lower() in property_filter_lower
        ]
        print(f"Filtering to {len(source_files)} files for properties: {property_filter}")
    
    report.total_files = len(source_files)
    print(f"Found {len(source_files)} source files to process")
    
    if not source_files:
        report.status = "FAILED"
        report.ended_at = datetime.now().isoformat()
        return report
    
    # Transform each file
    print("\n=== Transforming files ===")
    all_unmapped: set[str] = set()
    
    for i, source_path in enumerate(source_files, 1):
        property_code = extract_property_code_from_filename(source_path.name)
        if not property_code:
            print(f"[{i}/{len(source_files)}] [WARN] Could not extract property code from: {source_path.name}")
            continue
        
        output_filename = f"yardi_import__{property_code}__{report_month}.csv"
        output_path = import_template_dir / output_filename
        
        print(f"[{i}/{len(source_files)}] {property_code}")
        
        result = transform_csv_file(
            input_path=source_path,
            output_path=output_path,
            property_code=property_code,
            account_mapping=account_mapping,
            account_corrections=account_corrections,
        )
        
        # Apply cash account corrections (FINAL STEP)
        if result.status == "success" and property_code.lower() in cash_account_mapping:
            cash_description_mapping = cash_account_mapping[property_code.lower()]
            cash_corrections = apply_cash_account_corrections(
                csv_path=output_path,
                property_code=property_code,
                cash_description_mapping=cash_description_mapping,
            )
            result.cash_codes_fixed = len(cash_corrections)
            report.all_cash_corrections.extend(cash_corrections)
            report.total_cash_codes_fixed += len(cash_corrections)
        
        report.results.append(result)
        
        if result.status == "success":
            report.success_count += 1
            report.total_rows += result.row_count
            report.total_codes_fixed += result.codes_fixed
            
            if result.unmapped_descriptions:
                all_unmapped.update(result.unmapped_descriptions)
            
            status_msg = f"  [OK] {result.row_count} rows"
            if result.codes_fixed > 0:
                status_msg += f", {result.codes_fixed} codes fixed"
            if result.cash_codes_fixed > 0:
                status_msg += f", {result.cash_codes_fixed} cash codes fixed"
            if result.unmapped_descriptions:
                status_msg += f", {len(result.unmapped_descriptions)} unmapped"
            print(status_msg)
        else:
            report.error_count += 1
            print(f"  [ERR] Error: {result.error_message}")
    
    # =========================================================================
    # COMPILE FILES BY READING FROM DISK (ensures consistency)
    # =========================================================================
    # Instead of building compiled files from in-memory data, we read from the
    # individual files on disk. This guarantees the compiled file matches the
    # individual files exactly.
    
    if skip_compile:
        print("\n=== Skipping compiled file generation (--skip-compile) ===")
    else:
        # Copy individual Jay property files to Output/ first
        print("\n=== Generating individual Jay property files ===")
        for prop_code in sorted(jay_facilities):
            prop_file = import_template_dir / f"yardi_import__{prop_code}__{report_month}.csv"
            if prop_file.exists():
                # Copy to root output folder
                individual_path = output_dir / f"yardi_import__{prop_code}__{report_month}.csv"
                with prop_file.open("r", newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
                with individual_path.open("w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
                report.jay_property_files.append(str(individual_path))
                print(f"  [OK] {prop_code}: {individual_path.name} ({len(rows)} rows)")
        
        # Build compiled files by reading from individual files on disk
        print("\n=== Generating compiled files (from individual files) ===")
        
        # All facilities combined - read from import_template/
        all_transformed_rows = []
        for source_path in sorted(import_template_dir.glob(f"yardi_import__*__{report_month}.csv")):
            with source_path.open("r", newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
                all_transformed_rows.extend(rows)
        
        compiled_path = output_dir / f"yardi_import_compiled__{report_month}.csv"
        with compiled_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(all_transformed_rows)
        report.compiled_file = str(compiled_path)
        print(f"  [OK] Compiled all: {compiled_path.name} ({len(all_transformed_rows)} rows)")
        
        # Jay-only facilities - read from Output/ (the files we just copied)
        jay_transformed_rows = []
        for prop_code in sorted(jay_facilities):
            jay_file = output_dir / f"yardi_import__{prop_code}__{report_month}.csv"
            if jay_file.exists():
                with jay_file.open("r", newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
                    jay_transformed_rows.extend(rows)
        
        jay_path = output_dir / f"yardi_import_Jay__{report_month}.csv"
        with jay_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(jay_transformed_rows)
        report.jay_file = str(jay_path)
        print(f"  [OK] Jay combined: {jay_path.name} ({len(jay_transformed_rows)} rows)")
    
    # Generate cash corrections report
    if report.all_cash_corrections:
        print("\n=== Generating cash corrections report ===")
        corrections_path = output_dir / f"cash_account_corrections__{report_month}.csv"
        with corrections_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "property_code",
                "date",
                "original_code",
                "corrected_code",
                "description",
                "amount",
            ])
            writer.writeheader()
            for corr in report.all_cash_corrections:
                writer.writerow({
                    "property_code": corr.property_code,
                    "date": corr.date,
                    "original_code": corr.original_code,
                    "corrected_code": corr.corrected_code,
                    "description": corr.description,
                    "amount": corr.amount,
                })
        report.cash_corrections_file = str(corrections_path)
        print(f"  [OK] Cash corrections report: {corrections_path.name} ({len(report.all_cash_corrections)} corrections)")
    
    # Report unmapped descriptions
    report.all_unmapped_descriptions = sorted(all_unmapped)
    if all_unmapped:
        print(f"\n=== Unmapped descriptions ({len(all_unmapped)}) ===")
        for desc in sorted(all_unmapped):
            print(f"  - {desc}")
    
    # Finalize report
    report.ended_at = datetime.now().isoformat()
    report.status = "COMPLETED" if report.error_count == 0 else "PARTIAL"
    
    return report


def print_banner(title: str) -> None:
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_summary(report: TransformReport) -> None:
    print("\n" + "=" * 70)
    print("  TRANSFORM SUMMARY")
    print("=" * 70)
    print(f"  Status:        {report.status}")
    print(f"  Files:         {report.total_files}")
    print(f"  Success:       {report.success_count}")
    print(f"  Errors:        {report.error_count}")
    print(f"  Total Rows:    {report.total_rows}")
    print(f"  Codes Fixed:   {report.total_codes_fixed}")
    if report.total_cash_codes_fixed > 0:
        print(f"  Cash Codes Fixed: {report.total_cash_codes_fixed}")
    if report.all_unmapped_descriptions:
        print(f"  Unmapped:      {len(report.all_unmapped_descriptions)} descriptions")
    print(f"  Compiled:      {Path(report.compiled_file).name if report.compiled_file else 'N/A'}")
    print(f"  Jay File:      {Path(report.jay_file).name if report.jay_file else 'N/A'}")
    if report.jay_property_files:
        print(f"  Jay Properties: {len(report.jay_property_files)} individual files")
    if report.cash_corrections_file:
        print(f"  Cash Corrections: {Path(report.cash_corrections_file).name}")
    print("=" * 70)
    print(f"FINAL_MARKER: {report.status}")


def main():
    global DEBUG
    
    parser = argparse.ArgumentParser(description="Transform Edge GL CSVs to Yardi import format")
    parser.add_argument("--month", required=True, help="Month folder name (e.g., '12. Dec')")
    parser.add_argument("--property", "-p", nargs="+", help="Process only specific property code(s) (e.g., -p ssvenice or -p ephss ephss2)")
    parser.add_argument("--skip-compile", action="store_true", help="Skip regenerating compiled files")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    DEBUG = args.debug
    
    # Build title
    title = f"Edge to Yardi Transform - {args.month}"
    if args.property:
        title += f" (properties: {', '.join(args.property)})"
    print_banner(title)
    
    report = run_transform_workflow(
        month_folder=args.month,
        property_filter=args.property,
        skip_compile=args.skip_compile,
    )
    print_summary(report)


if __name__ == "__main__":
    main()
