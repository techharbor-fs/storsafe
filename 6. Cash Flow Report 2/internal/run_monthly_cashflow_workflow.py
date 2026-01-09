"""Run the full Cash Flow Report 2 workflow (single entrypoint).

This script exists so we don't have to guess which file is the "main" one.

Workflow:
1) Prepare/rebuild the target workbook (copy template tabs + upload exports)
2) Generate formulas + apply row highlighting in PORTFOLIO CASH FLOW

Usage (example):
  python run_monthly_cashflow_workflow.py \
    --month-folder "11. Nov" \
    --target-sheet "https://docs.google.com/spreadsheets/d/<id>/edit" \
    --confirm

Notes:
- Requires Google service account env vars (same as the underlying scripts).
- For safety, default is dry-run unless --confirm is provided.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


MONTH_NAMES = {
    "JAN": "January",
    "FEB": "February",
    "MAR": "March",
    "APR": "April",
    "MAY": "May",
    "JUN": "June",
    "JUL": "July",
    "AUG": "August",
    "SEP": "September",
    "OCT": "October",
    "NOV": "November",
    "DEC": "December",
}


def _month_abbrev_from_folder(month_folder: str) -> str:
    # Expected: "11. Nov" -> "NOV" (fallback: last token uppercased)
    text = (month_folder or "").strip()
    if not text:
        raise ValueError("month_folder is required")
    tail = text.split()[-1]
    mon3 = tail[:3].upper()
    if mon3 not in MONTH_NAMES:
        raise ValueError(f"Could not parse month abbrev from folder: {month_folder!r}")
    return mon3


def _extract_sheet_id(link_or_id: str) -> str:
    text = (link_or_id or "").strip()
    if not text:
        raise ValueError("target-sheet is required")
    m = __import__("re").search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", text)
    if m:
        return m.group(1)
    return text


def _run(cmd: list[str]) -> None:
    print("\n=== RUN ===")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--month-folder",
        required=True,
        help="Month folder under this directory (e.g., '11. Nov')",
    )
    parser.add_argument(
        "--target-sheet",
        required=True,
        help="Target Google Sheet link or ID",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually modify the target spreadsheet (default is dry-run)",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Skip copying tabs; only upload values into existing HA-CF tabs.",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Copy tabs and set formatting, but do not upload HA-CF values.",
    )
    parser.add_argument(
        "--skip-month-end",
        action="store_true",
        help="Skip Month End List checks and highlighting.",
    )
    parser.add_argument(
        "--assume-yes",
        action="store_true",
        help="Skip confirmation prompt for the generator.",
    )
    parser.add_argument(
        "--run-generator-in-dry-run",
        action="store_true",
        help="Also run the generator even when --confirm is not provided. By default, dry-run only runs the prepare step.",
    )

    # v1 statement builder integration (2. Cash Flow Report)
    parser.add_argument(
        "--skip-v1",
        action="store_true",
        help="Skip generating v1-style Cash Flow Report (All) statement tabs.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Year label for the v1 report title (optional; defaults to v1 script default).",
    )
    
    # Modular workflow control (run only specific steps)
    parser.add_argument(
        "--only-prepare",
        action="store_true",
        help="Run ONLY the prepare step (skip v1 and v2 generators).",
    )
    parser.add_argument(
        "--only-v1",
        action="store_true",
        help="Run ONLY v1 generator (skip prepare and v2). Requires prepare already completed.",
    )
    parser.add_argument(
        "--only-v2",
        action="store_true",
        help="Run ONLY v2 generator (skip prepare and v1). Requires prepare already completed.",
    )
    parser.add_argument(
        "--skip-v2",
        action="store_true",
        help="Skip v2 PORTFOLIO CASH FLOW generator (only run prepare and v1).",
    )
    
    args = parser.parse_args()
    
    # Validate mutually exclusive flags
    only_flags = [args.only_prepare, args.only_v1, args.only_v2]
    if sum(only_flags) > 1:
        parser.error("Cannot use multiple --only-* flags together. Choose one: --only-prepare, --only-v1, or --only-v2")
    
    if args.only_v1 and args.skip_v1:
        parser.error("Cannot use --only-v1 and --skip-v1 together")
    
    if args.only_v2 and args.skip_v2:
        parser.error("Cannot use --only-v2 and --skip-v2 together")

    here = Path(__file__).resolve().parent
    prepare = here / "prepare_monthly_cashflow_workbook.py"
    generate = here / "generate_property_cashflow_report.py"

    v1_script = (here.parent.parent / "2. Cash Flow Report" / "generate_cashflow_report.py").resolve()

    mon3 = _month_abbrev_from_folder(args.month_folder)
    month_tab = f"HA-CF-{mon3}"
    month_label = MONTH_NAMES[mon3]
    month_title = mon3[:1] + mon3[1:].lower()

    prepare_cmd = [
        sys.executable,
        str(prepare),
        "--month-folder",
        args.month_folder,
        "--target-sheet",
        args.target_sheet,
    ]
    if args.confirm:
        prepare_cmd.append("--confirm")
    if args.skip_copy:
        prepare_cmd.append("--skip-copy")
    if args.skip_upload:
        prepare_cmd.append("--skip-upload")
    # Always delete non-required tabs as part of the workflow.
    prepare_cmd.append("--delete-other-tabs")

    generate_cmd = [
        sys.executable,
        str(generate),
        "--sheet-id",
        args.target_sheet,
        "--month-tab",
        month_tab,
        "--month-label",
        month_label,
    ]
    if args.skip_month_end:
        generate_cmd.append("--skip-month-end")
    if args.assume_yes:
        generate_cmd.append("--assume-yes")

    # Determine what to run based on --only-* flags
    run_prepare = not (args.only_v1 or args.only_v2)
    run_v1 = not (args.only_prepare or args.only_v2 or args.skip_v1)
    run_v2 = not (args.only_prepare or args.only_v1 or args.skip_v2)
    
    # Execute prepare step
    if run_prepare:
        _run(prepare_cmd)
    else:
        print(f"\n[SKIPPED] Prepare step (--only-{args.only_v1 and 'v1' or 'v2'} flag active)")

    # Optional: build v1-style statement tabs inside the same target workbook.
    # The v1 source tabs (HA-CF-*, HA-BS-*) are now uploaded by prepare_monthly_cashflow_workbook.py.
    allow_writes = bool(args.confirm or args.run_generator_in_dry_run or args.only_v1 or args.only_v2)
    if run_v1 and allow_writes:
        env = os.environ.copy()
        env["CF_SPREADSHEET_ID"] = _extract_sheet_id(args.target_sheet)
        env["CF_MONTH"] = month_title
        if args.year is not None:
            env["CF_YEAR"] = str(args.year)

        # Run v1 generator twice: monthly + ytd.
        for report_type in ("monthly", "ytd"):
            env["CF_REPORT_TYPE"] = report_type
            cmd = [sys.executable, str(v1_script)]
            print("\n=== RUN ===")
            print(" ".join(cmd))
            subprocess.run(cmd, check=True, env=env)
    elif run_v1:
        print("\n[SKIPPED] v1 generator (no --confirm or --only-v1 flag)")

    # In dry-run mode, prepare does not actually create/copy tabs, so the generator
    # will often fail due to missing worksheets. Default to skipping generator.
    if not allow_writes and not args.only_v2:
        print("\n[DRY RUN] Skipping v2 generator (no changes were applied in prepare step).")
        print("Re-run with --confirm to run the full end-to-end workflow.")
        print("(Or pass --run-generator-in-dry-run if the target sheet is already prepared.)")
        print("\n=== RUN END ===")
        print("status: DRY_RUN_COMPLETED")
        return

    if run_v2:
        _run(generate_cmd)
    else:
        print(f"\n[SKIPPED] v2 PORTFOLIO CASH FLOW generator (--only-{args.only_prepare and 'prepare' or 'v1'} or --skip-v2 flag active)")

    print("\n=== RUN END ===")
    print("status: COMPLETED")


if __name__ == "__main__":
    main()
