"""Delete unused/legacy tabs from the Cash Flow Report 2 Google Sheet.

Safety-first: by default this only targets clearly legacy tabs created during earlier
import attempts (e.g., YARDI-RAW-* and HA-CF-RAW-*). It prints a plan and requires
--confirm to actually delete anything.

Usage:
  python cleanup_unused_tabs.py --sheet-id <link_or_id> --confirm

Optional:
  --include-pattern <regex>   Additional title regex(es) to delete (repeatable)
  --exclude-pattern <regex>   Title regex(es) to protect even if matched

"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials


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


@dataclass(frozen=True)
class SheetTab:
    title: str
    sheet_id: int
    index: int


def _list_tabs(ss: gspread.Spreadsheet) -> list[SheetTab]:
    meta = ss.fetch_sheet_metadata()
    out: list[SheetTab] = []
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        out.append(
            SheetTab(
                title=str(props.get("title", "")),
                sheet_id=int(props.get("sheetId")),
                index=int(props.get("index", 0)),
            )
        )
    out.sort(key=lambda t: t.index)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-id", default="", help="Google Sheet link or ID")
    parser.add_argument(
        "--include-pattern",
        action="append",
        default=[],
        help="Regex for additional tab titles to delete (repeatable)",
    )
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=[],
        help="Regex for tab titles to protect even if matched (repeatable)",
    )
    parser.add_argument("--confirm", action="store_true", help="Actually delete tabs")
    args = parser.parse_args()

    sheet_id = _extract_sheet_id(args.sheet_id)
    if not sheet_id:
        entered = input(f"Paste Google Sheet link/ID [default: {NOV_SHEET_DEFAULT}]: ").strip()
        sheet_id = _extract_sheet_id(entered) or NOV_SHEET_DEFAULT

    creds_path = _resolve_service_account_file()
    email = _service_account_email(creds_path)
    if email:
        print(f"Service account: {email}")
        print("Ensure the spreadsheet is shared with this email.")

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)

    include_patterns = [
        r"^YARDI-RAW-",
        r"^HA-CF-RAW-",
    ] + list(args.include_pattern)

    exclude_patterns = list(args.exclude_pattern)

    include_res = [re.compile(pat, re.IGNORECASE) for pat in include_patterns]
    exclude_res = [re.compile(pat, re.IGNORECASE) for pat in exclude_patterns]

    tabs = _list_tabs(ss)
    print("\nCurrent tabs:")
    for t in tabs:
        print(f"  [{t.index:02d}] {t.title} (sheetId={t.sheet_id})")

    to_delete: list[SheetTab] = []
    for t in tabs:
        if any(r.search(t.title) for r in exclude_res):
            continue
        if any(r.search(t.title) for r in include_res):
            to_delete.append(t)

    print("\nDelete candidates:")
    if not to_delete:
        print("  (none matched patterns)")
        return

    for t in to_delete:
        print(f"  - {t.title} (sheetId={t.sheet_id})")

    if not args.confirm:
        print("\n[DRY RUN] No tabs deleted. Re-run with --confirm to delete.")
        return

    print("\nDeleting tabs...")
    for t in to_delete:
        print(f"  Deleting: {t.title}")
        ws = ss.get_worksheet_by_id(t.sheet_id)
        if ws is None:
            # fallback by title
            ws = ss.worksheet(t.title)
        ss.del_worksheet(ws)

    print("\n✅ Cleanup complete.")


if __name__ == "__main__":
    main()
