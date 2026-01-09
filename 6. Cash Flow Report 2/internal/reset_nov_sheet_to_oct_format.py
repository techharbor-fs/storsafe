"""Reset the November cashflow spreadsheet tabs to match the October sample/master.

This uses Google Sheets' native sheet copy, which preserves formatting, borders,
fonts, colors, frozen panes, row/column sizes, conditional formatting, etc.

Workflow:
1) Delete existing target tabs (if present)
2) Copy the master tabs into the target spreadsheet
3) Rename HA-CF-OCT -> the desired month tab (default: HA-CF-NOV)
4) Optionally delete Sheet1

NOTE: Copying sheets also copies October values/formulas. After running this,
re-upload the HA-CF exports and re-run the generator.

Usage:
  python reset_nov_sheet_to_oct_format.py --target-sheet <link_or_id> --confirm

"""

from __future__ import annotations

import argparse
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


MASTER_SHEET_ID = "1iZNLklMpAPeVo57nJVFfGBqUmQ3PD_bow4IlYOvtQj0"  # Oct sample/master
NOV_SHEET_DEFAULT = "160onO2dxp7fewgcibKoQ9biFH0qW69wg215J9phMVSs"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _extract_sheet_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    marker = "/spreadsheets/d/"
    if marker in value:
        after = value.split(marker, 1)[1]
        return after.split("/", 1)[0]
    return value


def _resolve_service_account_file() -> str:
    service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        temp_json_path = Path(tempfile.gettempdir()) / "service_account.json"
        temp_json_path.write_text(json.dumps(json.loads(service_account_json)), encoding="utf-8")
        return str(temp_json_path)

    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("SERVICE_ACCOUNT_FILE")
    if not env_path:
        raise RuntimeError(
            "Missing Google service account credentials. Set SERVICE_ACCOUNT_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS/SERVICE_ACCOUNT_FILE."
        )
    return env_path


def _service_account_email(creds_path: str) -> str | None:
    try:
        data = json.loads(Path(creds_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    email = data.get("client_email")
    return str(email).strip() if email else None


def _maybe_delete_tab(ss: gspread.Spreadsheet, title: str, *, dry_run: bool) -> None:
    try:
        ws = ss.worksheet(title)
    except Exception:
        return
    if dry_run:
        print(f"  [DRY RUN] Would delete tab: {title}")
        return
    print(f"  Deleting existing tab: {title}")
    ss.del_worksheet(ws)


def _make_unique_title(ss: gspread.Spreadsheet, desired: str) -> str:
    existing = set(ss.worksheets())
    # gspread worksheets() returns Worksheet objects; compare by title
    existing_titles = {w.title for w in ss.worksheets()}
    if desired not in existing_titles:
        return desired
    i = 2
    while True:
        candidate = f"{desired} ({i})"
        if candidate not in existing_titles:
            return candidate
        i += 1


def _maybe_rename_tab(ss: gspread.Spreadsheet, title: str, new_title: str, *, dry_run: bool) -> str | None:
    try:
        ws = ss.worksheet(title)
    except Exception:
        return None
    unique_title = _make_unique_title(ss, new_title)
    if dry_run:
        print(f"  [DRY RUN] Would rename tab: {title} -> {unique_title}")
        return unique_title
    print(f"  Renaming existing tab: {title} -> {unique_title}")
    ws.update_title(unique_title)
    return unique_title


def _copy_tab(src_ss: gspread.Spreadsheet, dst_ss: gspread.Spreadsheet, src_title: str, dst_title: str, *, dry_run: bool) -> None:
    print(f"  Copying: {src_title} -> {dst_title}")
    if dry_run:
        return

    src_ws = src_ss.worksheet(src_title)
    copy_result = src_ws.copy_to(dst_ss.id)
    if isinstance(copy_result, dict):
        new_sheet_id = copy_result.get("sheetId")
    else:
        new_sheet_id = copy_result

    if new_sheet_id is None:
        raise RuntimeError(f"Unexpected copy result for {src_title}: {copy_result!r}")

    new_ws = dst_ss.get_worksheet_by_id(int(new_sheet_id))
    if new_ws is None:
        raise RuntimeError(f"Copied sheet not found by id: {new_sheet_id}")
    new_ws.update_title(dst_title)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-sheet", default="", help="Target (November) Google Sheet link or ID")
    parser.add_argument("--master-sheet", default=MASTER_SHEET_ID, help="Master (October sample) sheet link or ID")
    parser.add_argument("--month-tab", default="HA-CF-NOV", help="Target month tab name (e.g., HA-CF-NOV)")
    parser.add_argument("--delete-sheet1", action="store_true", help="Delete a tab named Sheet1 if present")
    parser.add_argument("--confirm", action="store_true", help="Actually perform deletions/copies")
    args = parser.parse_args()

    target_id = _extract_sheet_id(args.target_sheet)
    if not target_id:
        entered = input(f"Paste TARGET sheet link/ID [default: {NOV_SHEET_DEFAULT}]: ").strip()
        target_id = _extract_sheet_id(entered) or NOV_SHEET_DEFAULT

    master_id = _extract_sheet_id(args.master_sheet) or MASTER_SHEET_ID

    creds_path = _resolve_service_account_file()
    email = _service_account_email(creds_path)
    if email:
        print(f"Service account: {email}")
        print("Ensure BOTH spreadsheets are shared with this email.")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)

    src_ss = gc.open_by_key(master_id)
    dst_ss = gc.open_by_key(target_id)

    dry_run = not args.confirm

    # Tab mapping: source -> target
    mappings = [
        ("Property Codes", "Property Codes"),
        ("PORTFOLIO CASH FLOW", "PORTFOLIO CASH FLOW"),
        ("HA-CF-OCT", args.month_tab),
        ("HA-CF-3MOS", "HA-CF-3MOS"),
        ("HA-CF-YTD", "HA-CF-YTD"),
        ("Month End Reports", "Month End Reports"),
    ]

    print("\nPlanned operations:")
    for _, dst_title in mappings:
        print(f"  - Replace tab: {dst_title}")
    if args.delete_sheet1:
        print("  - Delete tab: Sheet1")

    if dry_run:
        print("\n[DRY RUN] No changes will be made. Re-run with --confirm to apply.")

    # Safety-first approach:
    # 1) Rename existing target tabs out of the way (avoids collisions)
    # 2) Copy master tabs in (preserves formatting)
    # 3) Delete the renamed legacy tabs and Sheet1

    print("\nRenaming existing target tabs (if present)...")
    renamed_old_titles: list[str] = []
    for _, dst_title in mappings:
        renamed = _maybe_rename_tab(dst_ss, dst_title, f"OLD__{dst_title}", dry_run=dry_run)
        if renamed:
            renamed_old_titles.append(renamed)

    print("\nCopying master tabs into target...")
    for src_title, dst_title in mappings:
        _copy_tab(src_ss, dst_ss, src_title, dst_title, dry_run=dry_run)

    print("\nDeleting replaced tabs...")
    for old_title in renamed_old_titles:
        _maybe_delete_tab(dst_ss, old_title, dry_run=dry_run)

    if args.delete_sheet1:
        _maybe_delete_tab(dst_ss, "Sheet1", dry_run=dry_run)

    if dry_run:
        print("\n✅ DRY RUN complete.")
    else:
        print("\n✅ Reset complete.")


if __name__ == "__main__":
    main()
