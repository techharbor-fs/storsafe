"""
SMS Monthly Distribution Workflow Launcher

Single entrypoint for the SMS monthly distribution report workflow.

Workflow Steps:
  1. compile    - Compile downloaded reports into standard Financial Report format
  2. distribute - Generate distribution recommendation workbooks
  3. balances   - Apply cash balances to distribution workbooks
  4. email      - Send distribution emails (dry-run by default)

Usage:
  # Run specific step
  py -3 run_sms_monthly_workflow.py --step compile --month "12. Dec" --report-date "12.31.25"
  py -3 run_sms_monthly_workflow.py --step distribute --month "12. Dec"
  py -3 run_sms_monthly_workflow.py --step balances --month "12. Dec"
  py -3 run_sms_monthly_workflow.py --step email --month "12. Dec" [--send]

  # Run full workflow (all steps)
  py -3 run_sms_monthly_workflow.py --month "12. Dec" --report-date "12.31.25"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INTERNAL_DIR = SCRIPT_DIR / "internal"
REPORTS_BASE = SCRIPT_DIR / ".Reports"


# Month abbreviations for date calculation
MONTH_INFO = {
    "jan": (1, 31), "feb": (2, 28), "mar": (3, 31), "apr": (4, 30),
    "may": (5, 31), "jun": (6, 30), "jul": (7, 31), "aug": (8, 31),
    "sep": (9, 30), "oct": (10, 31), "nov": (11, 30), "dec": (12, 31),
}


def parse_month_folder(month_folder: str) -> tuple[str, int, int]:
    """
    Parse month folder like '12. Dec' into (folder_name, month_num, last_day).
    Returns the folder name, month number, and typical last day of month.
    """
    parts = month_folder.strip().split()
    if len(parts) < 2:
        raise ValueError(f"Invalid month folder format: {month_folder}")
    
    month_abbr = parts[-1].lower()[:3]
    if month_abbr not in MONTH_INFO:
        raise ValueError(f"Could not parse month from: {month_folder}")
    
    month_num, last_day = MONTH_INFO[month_abbr]
    return month_folder, month_num, last_day


def infer_report_date(month_folder: str, year: int = 25) -> str:
    """Infer report date from month folder. E.g., '12. Dec' -> '12.31.25'"""
    _, month_num, last_day = parse_month_folder(month_folder)
    return f"{month_num:02d}.{last_day}.{year}"


def infer_report_month(month_folder: str, year: int = 2025) -> str:
    """Infer report month from month folder. E.g., '12. Dec' -> '2025-12'"""
    _, month_num, _ = parse_month_folder(month_folder)
    return f"{year}-{month_num:02d}"


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return True if successful."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print(f"\nERROR: {description} failed with exit code {result.returncode}")
        return False
    
    return True


def step_compile(month_folder: str, report_date: str) -> bool:
    """Step 1: Compile downloaded reports into Financial Report format."""
    reports_folder = REPORTS_BASE / month_folder
    
    if not reports_folder.exists():
        print(f"ERROR: Reports folder not found: {reports_folder}")
        return False
    
    cmd = [
        sys.executable,
        str(INTERNAL_DIR / "compile_downloaded_reports.py"),
        "--reports-folder", str(reports_folder),
        "--report-date", report_date,
    ]
    
    return run_command(cmd, "Compile Downloaded Reports")


def step_distribute(month_folder: str, report_date: str) -> bool:
    """Step 2: Generate distribution recommendation workbooks."""
    reports_folder = REPORTS_BASE / month_folder
    report_month = infer_report_month(month_folder)
    
    # Convert report_date from MM.DD.YY to YYYY-MM-DD
    # e.g., "12.31.25" -> "2025-12-31"
    parts = report_date.split(".")
    if len(parts) == 3:
        mm, dd, yy = parts
        current_balance_date = f"20{yy}-{mm}-{dd}"
    else:
        current_balance_date = report_date  # fallback
    
    cmd = [
        sys.executable,
        str(INTERNAL_DIR / "generate_monthly_distribution_reports.py"),
        "--reports-folder", str(reports_folder),
        "--report-month", report_month,
        "--current-balance-date", current_balance_date,
    ]
    
    return run_command(cmd, "Generate Distribution Recommendations")


def step_balances(month_folder: str) -> bool:
    """Step 3: Apply cash balances to distribution workbooks."""
    reports_folder = REPORTS_BASE / month_folder
    bank_balances_file = reports_folder / "bank_balances.txt"
    
    if not bank_balances_file.exists():
        print(f"ERROR: bank_balances.txt not found in {reports_folder}")
        print("Create bank_balances.txt with format:")
        print("  Property: Amount")
        print("  e.g., Cary: 60419.11")
        return False
    
    # Parse bank_balances.txt
    balances = []
    with open(bank_balances_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                prop, amount = line.split(":", 1)
                balances.append(f"{prop.strip()}={amount.strip()}")
    
    if not balances:
        print("ERROR: No balances found in bank_balances.txt")
        return False
    
    apply_script = INTERNAL_DIR / "apply_cash_balances.py"
    
    if not apply_script.exists():
        print(f"WARNING: {apply_script} not found")
        print("Cash balances will need to be applied manually or script needs to be created.")
        return False
    
    cmd = [
        sys.executable,
        str(apply_script),
        "--reports-folder", str(reports_folder),
    ]
    for balance in balances:
        cmd.extend(["--balance", balance])
    
    return run_command(cmd, "Apply Cash Balances")


def step_email(month_folder: str, send: bool = False) -> bool:
    """Step 4: Send distribution emails."""
    reports_folder = REPORTS_BASE / month_folder
    report_month = infer_report_month(month_folder)
    
    cmd = [
        sys.executable,
        str(INTERNAL_DIR / "send_distribution_emails.py"),
        "--reports-folder", str(reports_folder),
        "--report-month", report_month,
    ]
    
    if send:
        cmd.append("--send")
    
    description = "Send Distribution Emails" if send else "Send Distribution Emails (DRY RUN)"
    return run_command(cmd, description)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SMS Monthly Distribution Workflow Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compile downloaded reports
  py -3 run_sms_monthly_workflow.py --step compile --month "12. Dec" --report-date "12.31.25"

  # Generate distribution recommendations
  py -3 run_sms_monthly_workflow.py --step distribute --month "12. Dec"

  # Apply cash balances (reads from bank_balances.txt)
  py -3 run_sms_monthly_workflow.py --step balances --month "12. Dec"

  # Preview emails (dry run)
  py -3 run_sms_monthly_workflow.py --step email --month "12. Dec"

  # Send emails for real
  py -3 run_sms_monthly_workflow.py --step email --month "12. Dec" --send
        """
    )
    
    parser.add_argument(
        "--step",
        choices=["compile", "distribute", "balances", "email"],
        help="Run a specific step (omit to run full workflow)"
    )
    parser.add_argument(
        "--month",
        required=True,
        help="Month folder name (e.g., '12. Dec')"
    )
    parser.add_argument(
        "--report-date",
        help="Report date for filenames (e.g., '12.31.25'). Auto-inferred if not provided."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send emails (for email step)"
    )
    
    args = parser.parse_args()
    
    # Validate month folder exists
    month_folder = args.month
    reports_path = REPORTS_BASE / month_folder
    if not reports_path.exists():
        print(f"ERROR: Month folder not found: {reports_path}")
        print(f"\nAvailable months:")
        for folder in sorted(REPORTS_BASE.iterdir()):
            if folder.is_dir():
                print(f"  - {folder.name}")
        return 1
    
    # Infer report date if not provided
    report_date = args.report_date or infer_report_date(month_folder)
    
    print("=" * 60)
    print("SMS Monthly Distribution Workflow")
    print("=" * 60)
    print(f"Month Folder: {month_folder}")
    print(f"Report Date:  {report_date}")
    print(f"Step:         {args.step or 'FULL WORKFLOW'}")
    
    # Run specific step or full workflow
    if args.step == "compile":
        success = step_compile(month_folder, report_date)
    elif args.step == "distribute":
        success = step_distribute(month_folder, report_date)
    elif args.step == "balances":
        success = step_balances(month_folder)
    elif args.step == "email":
        success = step_email(month_folder, args.send)
    else:
        # Full workflow
        print("\nRunning full workflow...")
        
        # Step 1: Compile (skip if no downloaded files)
        if step_compile(month_folder, report_date):
            print("\n[Step 1/4] Compile: DONE")
        else:
            print("\n[Step 1/4] Compile: SKIPPED (no files or already compiled)")
        
        # Step 2: Generate distribution reports
        if not step_distribute(month_folder, report_date):
            print("\n[Step 2/4] Distribute: FAILED")
            return 1
        print("\n[Step 2/4] Distribute: DONE")
        
        # Step 3: Apply cash balances
        if step_balances(month_folder):
            print("\n[Step 3/4] Balances: DONE")
        else:
            print("\n[Step 3/4] Balances: SKIPPED (script missing or no balances)")
        
        # Step 4: Email (dry run by default)
        if not step_email(month_folder, args.send):
            print("\n[Step 4/4] Email: FAILED")
            return 1
        print("\n[Step 4/4] Email: DONE")
        
        success = True
    
    print("\n" + "=" * 60)
    if success:
        print("Workflow completed successfully!")
    else:
        print("Workflow completed with errors.")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
