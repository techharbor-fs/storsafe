"""Edge to Yardi Workflow Launcher.

This is the single obvious entrypoint for the Edge → Yardi workflow.
Run this script and select from the menu:

  [1] Phase 1: Download Edge GL Reports
      - Downloads GL by Day reports from StorEdge for all facilities
      - Requires Edge browser running with remote debugging (port 9222)
      - Outputs CSVs to: <month>/Output/edge_downloads/

  [2] Phase 2: Transform CSVs for Yardi Import
      - Transforms downloaded CSVs to Yardi import format
      - Fixes Column I (property_code) and Column K (account codes)
      - Outputs to: <month>/Output/import_template/ and compiled CSVs

Usage:
  python RUN_ME.py
  python RUN_ME.py --phase 2 --month-folder "12. Dec"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path
from tkinter import Tk
from tkinter.filedialog import askdirectory


def _list_month_folders(base_dir: Path) -> list[str]:
    """List month folders like '12. Dec' in the project directory."""
    out: list[str] = []
    try:
        for p in base_dir.iterdir():
            if not p.is_dir():
                continue
            name = p.name
            if name.lower() in {"internal", "data", "__pycache__"}:
                continue
            if "." in name and name.split(".", 1)[0].strip().isdigit():
                out.append(name)
    except Exception:
        return []
    out.sort()
    return out


def _default_report_month_from_folder(month_folder: str) -> str | None:
    """Convert '12. Dec' -> '2025-12' (uses current year)."""
    text = (month_folder or "").strip()
    if not text or "." not in text:
        return None
    try:
        month_num = int(text.split(".", 1)[0].strip())
    except Exception:
        return None
    if not (1 <= month_num <= 12):
        return None
    return f"{date.today().year}-{month_num:02d}"


def _select_month_folder(here: Path) -> tuple[str, str]:
    """Prompt user to select month folder via GUI. Returns (folder, report_month)."""
    print("\nOpening folder picker...")
    
    # Hide the tkinter root window
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    # Open folder picker starting at the project directory
    selected = askdirectory(
        title="Select Month Folder (e.g., 12. Dec)",
        initialdir=str(here),
    )
    
    root.destroy()
    
    if not selected:
        print("\nNo folder selected. Exiting.")
        raise SystemExit(2)
    
    # Get just the folder name (e.g., "12. Dec")
    folder = Path(selected).name
    
    default_report_month = _default_report_month_from_folder(folder)
    if not default_report_month:
        print(f"\nError: Could not determine report month from folder '{folder}'")
        print("Expected format: '<number>. <month>' (e.g., '12. Dec')")
        raise SystemExit(2)
    
    report_month = default_report_month
    print(f"Selected: {folder} → {report_month}")
    
    return folder, report_month


def _show_menu() -> int:
    """Display main menu and return selected option (1 or 2)."""
    print()
    print("=" * 50)
    print("  EDGE TO YARDI WORKFLOW")
    print("=" * 50)
    print()
    print("  [1] Phase 1: Download Edge GL Reports")
    print("      Downloads GL by Day reports from StorEdge")
    print()
    print("  [2] Phase 2: Transform CSVs for Yardi Import")
    print("      Transforms downloaded CSVs to Yardi format")
    print()
    print("  [0] Exit")
    print()
    
    choice = input("Select option: ").strip()
    
    try:
        return int(choice)
    except ValueError:
        return -1


def _run_phase1(here: Path, month_folder: str, report_month: str) -> int:
    """Run Phase 1: Download Edge GL Reports."""
    script = here / "internal" / "edge_report_downloader.py"
    
    if not script.exists():
        print(f"\nError: Script not found: {script}")
        return 1
    
    month_dir = here / month_folder
    output_dir = month_dir / "Output" / "edge_downloads"
    
    print()
    print("-" * 50)
    print("PHASE 1: Download Edge GL Reports")
    print("-" * 50)
    print(f"  Month folder: {month_folder}")
    print(f"  Report month: {report_month}")
    print(f"  Output dir:   {output_dir}")
    print()
    print("Prerequisites:")
    print("  - Edge browser running with: --remote-debugging-port=9222")
    print("  - Already logged into StorEdge")
    print()
    
    confirm = input("Continue? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("Cancelled.")
        return 0
    
    cmd = [
        sys.executable, str(script),
        "--report-month", report_month,
        "--output-dir", str(output_dir),
    ]
    
    return subprocess.call(cmd)


def _run_phase2(here: Path, month_folder: str, report_month: str) -> int:
    """Run Phase 2: Transform CSVs for Yardi Import."""
    script = here / "internal" / "transform_edge_to_yardi.py"
    
    if not script.exists():
        print(f"\nError: Script not found: {script}")
        return 1
    
    month_dir = here / month_folder
    input_dir = month_dir / "Output" / "edge_downloads"
    output_dir = month_dir / "Output"
    mapping_file = month_dir / "Input" / "account code mapping.csv"
    
    print()
    print("-" * 50)
    print("PHASE 2: Transform CSVs for Yardi Import")
    print("-" * 50)
    print(f"  Month folder:  {month_folder}")
    print(f"  Report month:  {report_month}")
    print(f"  Input dir:     {input_dir}")
    print(f"  Output dir:    {output_dir}")
    print(f"  Mapping file:  {mapping_file}")
    print()
    
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        print("  Run Phase 1 first to download the Edge GL reports.")
        return 1
    
    csv_count = len(list(input_dir.glob("*.csv")))
    if csv_count == 0:
        print(f"Error: No CSV files found in: {input_dir}")
        print("  Run Phase 1 first to download the Edge GL reports.")
        return 1
    
    print(f"Found {csv_count} CSV files to transform.")
    print()
    
    confirm = input("Continue? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("Cancelled.")
        return 0
    
    cmd = [
        sys.executable, str(script),
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--report-month", report_month,
    ]
    
    if mapping_file.exists():
        cmd.extend(["--mapping-file", str(mapping_file)])
    
    return subprocess.call(cmd)

def main() -> None:
    here = Path(__file__).resolve().parent
    
    parser = argparse.ArgumentParser(description="Edge to Yardi Workflow")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Phase to run (1=download, 2=transform)")
    parser.add_argument("--month-folder", help="Month folder (e.g., '12. Dec')")
    args = parser.parse_args()
    
    try:
        # If --phase provided, skip menu
        if args.phase:
            choice = args.phase
        else:
            choice = _show_menu()
        
        if choice == 0:
            print("Goodbye.")
            raise SystemExit(0)
        
        if choice not in (1, 2):
            print("Invalid option. Please enter 1, 2, or 0.")
            raise SystemExit(1)
        
        # Get month folder and report month
        if args.month_folder:
            month_folder = args.month_folder
            report_month = _default_report_month_from_folder(month_folder) or ""
            if not report_month:
                print(f"Error: Could not determine report month from folder '{month_folder}'")
                raise SystemExit(1)
        else:
            month_folder, report_month = _select_month_folder(here)
        
        if choice == 1:
            exit_code = _run_phase1(here, month_folder, report_month)
        else:  # choice == 2
            exit_code = _run_phase2(here, month_folder, report_month)
        
        raise SystemExit(exit_code)
        
    except KeyboardInterrupt:
        print("\nCancelled. Exiting.")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
