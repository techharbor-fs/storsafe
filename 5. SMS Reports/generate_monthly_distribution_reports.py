"""Generate SMS distribution recommendation workbooks for every property in a month folder."""
from __future__ import annotations

import argparse
import calendar
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

CURRENT_DIR = Path(__file__).resolve().parent
REPORTS_BASE = CURRENT_DIR / ".Reports"
HELPER_DIR = CURRENT_DIR / ".helper_artifacts"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from generate_distribution_report import generate_distribution_report  # type: ignore


# Month name to number mapping
MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class PropertyConfig:
    property_name: str
    output_label: str


PROPERTY_CONFIG: dict[str, PropertyConfig] = {
    "altoona": PropertyConfig("Altoona", "Altoona"),
    "cary": PropertyConfig("Cary", "Cary"),
    "crystal lake": PropertyConfig("Crystal Lake", "CLK"),
    "nfss": PropertyConfig("NFSS", "NFSS"),
}


ALIAS_NORMALIZATIONS = {
    "crytal": "crystal",
}


def get_available_months() -> list[Path]:
    """Get list of month folders in .Reports/, sorted by month number."""
    if not REPORTS_BASE.exists():
        return []
    
    folders = []
    for item in REPORTS_BASE.iterdir():
        if item.is_dir() and re.match(r"^\d+\.", item.name):
            folders.append(item)
    
    # Sort by the month number prefix
    return sorted(folders, key=lambda p: int(p.name.split(".")[0]))


def parse_folder_to_month(folder_name: str) -> tuple[int, int] | None:
    """Parse folder name like '11. Nov' to (year, month). Assumes current year."""
    match = re.match(r"^(\d+)\.\s*(\w+)", folder_name)
    if not match:
        return None
    
    month_num = int(match.group(1))
    month_abbrev = match.group(2).lower()[:3]
    
    # Validate month number matches abbreviation
    if month_abbrev in MONTH_NAMES:
        expected_num = MONTH_NAMES[month_abbrev]
        if month_num != expected_num:
            month_num = expected_num  # Trust the abbreviation
    
    # Determine year - assume current year, but if month > current month, use last year
    today = date.today()
    year = today.year
    if month_num > today.month:
        year -= 1
    
    return (year, month_num)


def select_folder_interactive() -> tuple[Path, str] | None:
    """Present interactive menu to select a month folder. Returns (folder_path, report_month)."""
    folders = get_available_months()
    
    if not folders:
        print(f"No month folders found in {REPORTS_BASE}")
        return None
    
    print("\n=== Available Month Folders ===\n")
    for i, folder in enumerate(folders, 1):
        # Count financial workbooks in folder
        wb_count = len(list(folder.glob("SMS-*Financial*.xlsx")))
        print(f"  {i}. {folder.name}  ({wb_count} Financial Reports)")
    
    print(f"\n  0. Cancel\n")
    
    while True:
        try:
            choice = input("Select folder number: ").strip()
            if choice == "0" or choice.lower() == "q":
                return None
            
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                selected = folders[idx]
                parsed = parse_folder_to_month(selected.name)
                if parsed:
                    year, month = parsed
                    report_month = f"{year}-{month:02d}"
                    return (selected, report_month)
                else:
                    print(f"Could not parse month from folder name: {selected.name}")
                    return None
            else:
                print(f"Please enter a number between 1 and {len(folders)}")
        except ValueError:
            print("Please enter a valid number")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate SMS distribution reports for all financial workbooks in a folder.",
    )
    parser.add_argument(
        "--reports-folder",
        type=Path,
        help="Folder containing the monthly SMS financial workbooks. If not provided, shows interactive selection.",
    )
    parser.add_argument(
        "--report-month",
        help="Reporting month in YYYY-MM format. Auto-detected from folder name if not provided.",
    )
    parser.add_argument(
        "--operating-hold",
        type=float,
        default=-10000.0,
        help="Operating hold value applied to cell A4 (default: -10000)",
    )
    parser.add_argument(
        "--b15-value",
        type=float,
        help="Optional value for cell B15 (leave blank to keep it empty)",
    )
    parser.add_argument(
        "--current-balance-date",
        help="Override the 'Current Balance @' date (YYYY-MM-DD). Defaults to the last day of the report month.",
    )
    return parser.parse_args()


def normalize_property_key(raw: str) -> str:
    key = raw.lower().replace("_", " ").replace("-", " ")
    for wrong, right in ALIAS_NORMALIZATIONS.items():
        key = key.replace(wrong, right)
    return " ".join(key.split())


def derive_property_config(financial_path: Path) -> PropertyConfig:
    stem = financial_path.stem
    if stem.lower().startswith("sms-"):
        stem = stem[4:]

    tokens: list[str] = []
    for token in stem.split():
        if any(char.isdigit() for char in token):
            break
        if token.lower() in {"financial", "report", "final", "report_final"}:
            break
        tokens.append(token)

    raw_name = " ".join(tokens) if tokens else stem
    key = normalize_property_key(raw_name)
    if key in PROPERTY_CONFIG:
        return PROPERTY_CONFIG[key]

    title = " ".join(word.capitalize() for word in key.split()) or "Unknown Property"
    return PropertyConfig(property_name=title, output_label=title)


def iter_financial_workbooks(reports_folder: Path) -> Iterable[Path]:
    return sorted(
        p for p in reports_folder.glob("SMS-*.xlsx") if "Financial" in p.name
    )


BALANCES_FILENAME = "bank_balances.txt"


def load_bank_balances(reports_folder: Path) -> dict[str, float]:
    """Load bank balances from bank_balances.txt in the reports folder.
    
    File format (one per line):
        Property: Amount
        # Comments start with #
    
    Returns dict mapping normalized property name to balance.
    """
    balances: dict[str, float] = {}
    balances_file = reports_folder / BALANCES_FILENAME
    
    if not balances_file.exists():
        return balances
    
    print(f"Loading bank balances from {BALANCES_FILENAME}...")
    
    for line_num, line in enumerate(balances_file.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if ":" not in line:
            print(f"  [WARN] Line {line_num}: Invalid format (missing colon): {line}")
            continue
        
        prop_name, amount_str = line.split(":", 1)
        prop_name = prop_name.strip()
        amount_str = amount_str.strip().replace(",", "").replace("$", "")
        
        try:
            amount = float(amount_str)
            # Normalize property name for matching
            key = normalize_property_key(prop_name)
            balances[key] = amount
            print(f"  {prop_name}: ${amount:,.2f}")
        except ValueError:
            print(f"  [WARN] Line {line_num}: Invalid amount: {amount_str}")
    
    print()
    return balances


def main() -> None:
    args = parse_args()
    
    # Determine reports folder and report month
    if args.reports_folder:
        reports_folder = args.reports_folder.resolve()
        if not reports_folder.exists():
            raise FileNotFoundError(reports_folder)
        
        # Auto-detect report month from folder name if not provided
        if args.report_month:
            report_month_str = args.report_month
        else:
            parsed = parse_folder_to_month(reports_folder.name)
            if parsed:
                year, month = parsed
                report_month_str = f"{year}-{month:02d}"
                print(f"Auto-detected report month: {report_month_str}")
            else:
                print("Could not auto-detect report month. Please provide --report-month.")
                return
    else:
        # Interactive selection
        result = select_folder_interactive()
        if not result:
            print("No folder selected. Exiting.")
            return
        reports_folder, report_month_str = result
        print(f"\nProcessing: {reports_folder.name} (Report month: {report_month_str})\n")

    report_year, report_month = map(int, report_month_str.split("-"))
    month_label = f"{report_month:02d}.{report_year}"
    last_day = calendar.monthrange(report_year, report_month)[1]
    default_balance_date = args.current_balance_date or f"{report_year}-{report_month:02d}-{last_day:02d}"

    # Load bank balances from file
    bank_balances = load_bank_balances(reports_folder)

    financial_files = list(iter_financial_workbooks(reports_folder))
    if not financial_files:
        print(f"No SMS financial workbooks found in {reports_folder}")
        return

    successes: list[str] = []
    failures: list[tuple[Path, Exception]] = []

    for workbook in financial_files:
        config = derive_property_config(workbook)
        output_name = f"{month_label} SMS - {config.output_label} Distribution recommendation.xlsx"
        output_path = reports_folder / output_name
        # Get balance for this property (from file or CLI arg)
        prop_key = normalize_property_key(config.property_name)
        b15_value = args.b15_value  # CLI arg takes precedence
        if b15_value is None and prop_key in bank_balances:
            b15_value = bank_balances[prop_key]
        
        try:
            generate_distribution_report(
                financial_path=workbook,
                property_name=config.property_name,
                report_month=report_month_str,
                output_path=output_path,
                operating_hold=args.operating_hold,
                b15_value=b15_value,
                current_balance_date=default_balance_date,
            )
            balance_note = f" (Balance: ${b15_value:,.2f})" if b15_value is not None else ""
            successes.append(f"{config.property_name} -> {output_name}{balance_note}")
        except Exception as exc:  # noqa: BLE001 - want full error report per workbook
            failures.append((workbook, exc))

    for entry in successes:
        print(f"[OK] {entry}")

    if failures:
        print("\nFailures:")
        for workbook, exc in failures:
            print(f"[ERROR] {workbook.name}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
