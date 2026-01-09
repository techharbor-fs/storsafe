"""Copy required template tabs from the master cashflow spreadsheet into a fresh monthly spreadsheet.

This enables running generate_property_cashflow_report.py on a new sheet by providing:
- PORTFOLIO CASH FLOW
- Property Codes
- Month End Reports (values only; formatting is not copied)

Usage:
  python copy_cashflow_template_tabs.py --target-sheet <link_or_id>

Notes:
- Spreadsheet must be shared with the service account.
- This copies VALUES only (not formatting). If you rely on Month End green cells,
  run the generator with --skip-month-end for fresh sheets.

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


MASTER_SHEET_ID = "1iZNLklMpAPeVo57nJVFfGBqUmQ3PD_bow4IlYOvtQj0"
NOV_SHEET_DEFAULT = "160onO2dxp7fewgcibKoQ9biFH0qW69wg215J9phMVSs"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TABS = ["PORTFOLIO CASH FLOW", "Property Codes", "Month End Reports"]


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


def _ensure_worksheet(ss: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        ws = ss.worksheet(title)
        if ws.row_count < rows or ws.col_count < cols:
            ws.resize(rows=max(rows, ws.row_count), cols=max(cols, ws.col_count))
        return ws
    except Exception:
        return ss.add_worksheet(title=title, rows=rows, cols=cols)


def _upload_table(ws: gspread.Worksheet, table: list[list[str]]) -> None:
    values = [["" if v is None else v for v in row] for row in table]
    rows = max(1, len(values))
    cols = max(1, max((len(r) for r in values), default=1))
    ws.resize(rows=rows, cols=cols)
    ws.update("A1", values, value_input_option="USER_ENTERED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-sheet", default="", help="Target sheet link or ID")
    parser.add_argument("--master-sheet", default=MASTER_SHEET_ID, help="Master template sheet link or ID")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite tabs if they already exist")
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
        print("Ensure both sheets are shared with this email.")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)

    master = gc.open_by_key(master_id)
    target = gc.open_by_key(target_id)

    for tab in TABS:
        print("\n" + "=" * 100)
        print("Copying tab:", tab)
        src_ws = master.worksheet(tab)
        data = src_ws.get_all_values()

        try:
            dst_ws = target.worksheet(tab)
            if not args.overwrite:
                print("  - exists in target; skipping (use --overwrite to replace)")
                continue
        except Exception:
            dst_ws = None

        rows = max(1, len(data))
        cols = max(1, max((len(r) for r in data), default=1))
        dst_ws = _ensure_worksheet(target, tab, rows=rows, cols=cols)
        _upload_table(dst_ws, data)
        print(f"  - copied {rows}x{cols}")

    print("\n✅ Template tabs copied.")


if __name__ == "__main__":
    main()
