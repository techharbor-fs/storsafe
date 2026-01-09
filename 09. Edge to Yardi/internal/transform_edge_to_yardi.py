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
        print(f"  ⚠️ Account code mapping not found: {mapping_path}")
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


def load_property_cash_account_mapping(mapping_path: Path) -> dict[str, str]:
    """Load property-specific cash account codes from CSV.
    
    Maps property_code -> correct_cash_account
    This corrects cases where Edge exports use wrong cash account codes.
    """
    if not mapping_path.exists():
        debug_print(f"Property cash account mapping not found: {mapping_path}")
        return {}
    
    mapping: dict[str, str] = {}
    with mapping_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prop_code = (row.get("property_code") or "").strip().lower()
            cash_code = (row.get("correct_cash_account") or "").strip()
            if prop_code and cash_code:
                mapping[prop_code] = cash_code
    
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
        print(f"  ⚠️ Facility order not found: {FACILITY_ORDER_PATH}")
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

def apply_cash_account_corrections(
    csv_path: Path,
    property_code: str,
    cash_account_code: str,
) -> list[CashCodeCorrection]:
    """Apply property-specific cash account code corrections.
    
    This is the FINAL transformation step that fixes incorrect cash account codes
    that appear in Edge exports. Modifies the CSV file in place.
    
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
        
        # Only correct if:
        # 1. Description indicates it's a cash transaction
        # 2. Current code is different from the correct code
        # 3. Current code starts with 11 (cash/bank accounts)
        if (is_cash_description(description) and 
            current_code != cash_account_code and
            current_code.startswith("11")):
            
            # Extract transaction date (column E, index 4)
            date_str = row[4] if len(row) > 4 else ""
            amount = row[COL_AMOUNT] if len(row) > COL_AMOUNT else ""
            
            corrections.append(CashCodeCorrection(
                property_code=property_code,
                date=date_str,
                original_code=current_code,
                corrected_code=cash_account_code,
                description=description,
                amount=amount,
            ))
            
            # Apply correction
            row[COL_ACCOUNT_CODE] = cash_account_code
            debug_print(f"Cash correction: {current_code} -> {cash_account_code} for {description}")
    
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
) -> TransformReport:
    """Run the full transformation workflow."""
    
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
    
    # Load property-specific cash account mapping
    cash_mapping_path = month_dir / "Input" / "property_cash_account_mapping.csv"
    cash_account_mapping = load_property_cash_account_mapping(cash_mapping_path)
    if cash_account_mapping:
        print(f"Loaded {len(cash_account_mapping)} property cash account mappings")
    
    facility_assignees = load_facility_assignees()
    jay_facilities = {k for k, v in facility_assignees.items() if v.lower() == "jay"}
    print(f"Found {len(jay_facilities)} facilities assigned to Jay")
    
    # Find source files
    print("\n=== Finding source files ===")
    source_files = sorted(edge_downloads_dir.glob("edge_gl_by_day__*__*.csv"))
    report.total_files = len(source_files)
    print(f"Found {len(source_files)} source files in edge_downloads/")
    
    if not source_files:
        report.status = "FAILED"
        report.ended_at = datetime.now().isoformat()
        return report
    
    # Transform each file
    print("\n=== Transforming files ===")
    all_transformed_rows: list[list[str]] = []
    jay_transformed_rows: list[list[str]] = []
    all_unmapped: set[str] = set()
    
    for i, source_path in enumerate(source_files, 1):
        property_code = extract_property_code_from_filename(source_path.name)
        if not property_code:
            print(f"[{i}/{len(source_files)}] ⚠️ Could not extract property code from: {source_path.name}")
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
            cash_code = cash_account_mapping[property_code.lower()]
            cash_corrections = apply_cash_account_corrections(
                csv_path=output_path,
                property_code=property_code,
                cash_account_code=cash_code,
            )
            result.cash_codes_fixed = len(cash_corrections)
            report.all_cash_corrections.extend(cash_corrections)
            report.total_cash_codes_fixed += len(cash_corrections)
        
        report.results.append(result)
        
        if result.status == "success":
            report.success_count += 1
            report.total_rows += result.row_count
            report.total_codes_fixed += result.codes_fixed
            
            # Add to compiled output
            with output_path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
                all_transformed_rows.extend(rows)
                
                # Check if this facility is assigned to Jay
                if property_code.lower() in jay_facilities:
                    jay_transformed_rows.extend(rows)
            
            if result.unmapped_descriptions:
                all_unmapped.update(result.unmapped_descriptions)
            
            status_msg = f"  ✓ {result.row_count} rows"
            if result.codes_fixed > 0:
                status_msg += f", {result.codes_fixed} codes fixed"
            if result.cash_codes_fixed > 0:
                status_msg += f", {result.cash_codes_fixed} cash codes fixed"
            if result.unmapped_descriptions:
                status_msg += f", {len(result.unmapped_descriptions)} unmapped"
            print(status_msg)
        else:
            report.error_count += 1
            print(f"  ✗ Error: {result.error_message}")
    
    # Write compiled CSVs
    print("\n=== Generating compiled files ===")
    
    # All facilities combined
    compiled_path = output_dir / f"yardi_import_compiled__{report_month}.csv"
    with compiled_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(all_transformed_rows)
    report.compiled_file = str(compiled_path)
    print(f"  ✓ Compiled all: {compiled_path.name} ({len(all_transformed_rows)} rows)")
    
    # Jay-only facilities
    jay_path = output_dir / f"yardi_import_Jay__{report_month}.csv"
    with jay_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(jay_transformed_rows)
    report.jay_file = str(jay_path)
    print(f"  ✓ Jay combined: {jay_path.name} ({len(jay_transformed_rows)} rows)")
    
    # Individual Jay property files (new requirement)
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
            print(f"  ✓ {prop_code}: {individual_path.name} ({len(rows)} rows)")
    
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
        print(f"  ✓ Cash corrections report: {corrections_path.name} ({len(report.all_cash_corrections)} corrections)")
    
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
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    DEBUG = args.debug
    
    print_banner(f"Edge to Yardi Transform - {args.month}")
    
    report = run_transform_workflow(month_folder=args.month)
    print_summary(report)


if __name__ == "__main__":
    main()
