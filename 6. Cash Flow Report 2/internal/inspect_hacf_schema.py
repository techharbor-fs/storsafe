"""Inspect HA-CF tabs in the shared Google Sheet.

This is a safe, read-only diagnostic to confirm:
- Which columns contain account codes / descriptions
- Which row contains property codes
- Whether required account codes exist
- Whether CFADS (the 'CASH FLOW' row) is detectable

Usage:
  python inspect_hacf_schema.py

Credentials:
- Set SERVICE_ACCOUNT_JSON (JSON string) OR
- Set GOOGLE_APPLICATION_CREDENTIALS / SERVICE_ACCOUNT_FILE (path)

"""

from __future__ import annotations

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

from hacf_utils import infer_layout, list_property_codes, find_account_row, required_codes


DEFAULT_SHEET_ID = "1iZNLklMpAPeVo57nJVFfGBqUmQ3PD_bow4IlYOvtQj0"
# Convenience default for current workflow (Nov 2025 spreadsheet shared by user)
DEFAULT_NOV_2025_SHEET_ID = "160onO2dxp7fewgcibKoQ9biFH0qW69wg215J9phMVSs"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TABS = ["HA-CF-OCT", "HA-CF-3MOS", "HA-CF-YTD"]


def _extract_sheet_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    # Accept full Google Sheets URLs.
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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheet-id",
        default=os.environ.get("CASHFLOW_SHEET_ID") or DEFAULT_NOV_2025_SHEET_ID,
        help="Google Sheet ID or full link (defaults to CASHFLOW_SHEET_ID env var)",
    )
    parser.add_argument(
        "--tabs",
        nargs="*",
        default=TABS,
        help="Tabs to inspect (default: HA-CF-OCT HA-CF-3MOS HA-CF-YTD)",
    )
    args = parser.parse_args()

    creds_path = _resolve_service_account_file()
    email = _service_account_email(creds_path)
    if email:
        print(f"Service account: {email}")

    # Interactive prompt (flow requirement): user can paste a link or sheet id.
    sheet_id = _extract_sheet_id(args.sheet_id)
    if not sheet_id:
        default_display = DEFAULT_NOV_2025_SHEET_ID
        entered = input(f"Paste Google Sheet link/ID [default: {default_display}]: ").strip()
        sheet_id = _extract_sheet_id(entered) or DEFAULT_NOV_2025_SHEET_ID

    if not sheet_id:
        raise SystemExit("Missing sheet id. Provide --sheet-id or paste one at the prompt.")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)

    print("\nAvailable tabs:")
    for ws in ss.worksheets():
        print(f"  - {ws.title}")

    for tab in args.tabs:
        print("\n" + "=" * 100)
        print(f"TAB: {tab}")
        try:
            ws = ss.worksheet(tab)
        except Exception:
            print(f"⚠️ Tab not found: {tab}")
            continue
        data = ws.get_all_values()

        layout = infer_layout(data)
        print("Layout:")
        print(f"  account_code_col: {layout.account_code_col}")
        print(f"  description_col:  {layout.description_col}")
        print(f"  property_code_row:{layout.property_code_row}")
        print(f"  period_row:       {layout.period_row}")
        print(f"  cfads_row:        {layout.cfads_row}")

        if layout.account_code_col is not None:
            start_col = layout.account_code_col + 2
        else:
            start_col = 2

        codes = list_property_codes(data, layout.property_code_row, start_col)
        print(f"Property codes detected: {len(codes)}")
        if codes:
            print("  sample:", ", ".join(codes[:12]))

        missing = []
        present = []
        for code in required_codes():
            row = find_account_row(data, code, layout.account_code_col)
            if row is None:
                missing.append(code)
            else:
                present.append((code, row))

        if present:
            print("Required codes present:")
            for code, row in present:
                print(f"  {code}: row {row + 1}")
        if missing:
            print("Missing required codes:")
            for code in missing:
                print(f"  {code}")


if __name__ == "__main__":
    main()
