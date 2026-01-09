"""Parasitic StorEdge Account Code Set automation.

Key capabilities:
- Attaches to an already-open Chrome/Edge via CDP (remote debugging).
- Finds the StorEdge Account Code Sets page you have open.
- Loads mapping data for each property tab from Google Sheets (skipping globals/epmss).
- For every property: skip if an Account Code Set already exists; otherwise create a new one.
- Types into the real UI and either cancels (DRY_RUN) or saves (real mode).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import Browser, Locator, Page, Playwright, sync_playwright

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
if service_account_json:
    temp_json_path = Path(tempfile.gettempdir()) / "service_account.json"
    temp_json_path.write_text(json.dumps(json.loads(service_account_json)), encoding="utf-8")
    SERVICE_ACCOUNT_FILE = str(temp_json_path)
else:
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("SERVICE_ACCOUNT_FILE")
    if not env_path:
        raise RuntimeError(
            "Missing Google service account credentials. Set SERVICE_ACCOUNT_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS/SERVICE_ACCOUNT_FILE."
        )
    SERVICE_ACCOUNT_FILE = env_path
SHEET_ID = "1DxP8RW3Q_e9kTqGkFnqCMwsaUKDOli_-Mg42YYuKI3I"

# Toggle between DRY_RUN (True) and real save mode (False).
DRY_RUN = False

GLOBAL_TABS = {"Edge", "Yardi-TB", "Edge-Normalized", "Property Codes"}
ALWAYS_SKIP_TABS = {"epmss"}


@dataclass
class AccountCodeRow:
    internal_code: str
    category: str
    subcategory: str
    description: str
    code: str


def connect_sheet() -> gspread.Spreadsheet:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def load_property_mapping(sh: gspread.Spreadsheet, sheet_title: str) -> Tuple[str, List[AccountCodeRow]]:
    """Load Account Code Set name (H2) and rows A:E from the given property tab."""
    ws = sh.worksheet(sheet_title)

    name_cell = ws.acell("H2").value or ""
    account_set_name = name_cell.strip()

    values = ws.get("A2:E200")

    rows: List[AccountCodeRow] = []
    for raw in values:
        while len(raw) < 5:
            raw.append("")
        a, b, c, d, e = (cell.strip() if isinstance(cell, str) else str(cell) for cell in raw)
        if not any([a, b, c, d, e]):
            continue
        rows.append(AccountCodeRow(a, b, c, d, e))

    return account_set_name, rows


def extract_facility_search_text(account_set_name: str) -> str:
    """Return the text to type into Facilities / Groups (prefix before " -")."""
    if not account_set_name:
        return ""
    return account_set_name.split(" -", 1)[0].strip()


def ask_debug_port() -> int:
    raw = input("Remote debugging port [9222]: ").strip()
    if not raw:
        return 9222
    try:
        return int(raw)
    except ValueError:
        print("Invalid port, defaulting to 9222.")
        return 9222


def attach_browser(port: int) -> Tuple[Browser, Page, Playwright]:
    """Attach to existing Chromium and pick the StorEdge page.

    Returns (browser, page, playwright_instance).
    Caller is responsible for pw.stop(), but should NOT close the real browser.
    """
    pw = sync_playwright().start()
    endpoint = f"http://localhost:{port}"
    print(f"Connecting to existing Chromium via CDP at {endpoint} ...")
    browser = pw.chromium.connect_over_cdp(endpoint)

    storedge_page: Optional[Page] = None
    for context in browser.contexts:
        for page in context.pages:
            title = (page.title() or "").lower()
            url = page.url.lower()
            if "storedge" in url or "storable edge" in title or "unified platform" in title:
                storedge_page = page
                break
        if storedge_page is not None:
            break

    if storedge_page is None:
        print("⚠️ Could not uniquely identify StorEdge tab; using first available page.")
        storedge_page = browser.contexts[0].pages[0]

    print(f"Attached to page: '{storedge_page.title()}' -> {storedge_page.url}")
    return browser, storedge_page, pw


def click_add_new_account_code_set(page: Page) -> None:
    """Open the 'Add new account code set' form from the list page."""
    print("- Clicking 'Add new account code set' ...")
    page.evaluate("window.scrollTo(0, 0)")

    locators = [
        page.locator("#settings > div:nth-child(3) > table > tbody > tr:nth-child(1) > td > a"),
        page.get_by_role("link", name="Add new account code set"),
        page.locator("table a", has_text="Add new account code set"),
        page.get_by_text("Add new account code set", exact=False),
    ]

    last_error: Optional[Exception] = None
    for attempt in range(3):
        locator = locators[min(attempt, len(locators) - 1)]
        try:
            locator.scroll_into_view_if_needed()
            locator.click(timeout=5000)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print("  ⚠️ 'Add new account code set' not clickable; scrolling and retrying ...")
            page.evaluate("window.scrollBy(0, 400)")
    else:
        raise last_error if last_error else RuntimeError("Could not click 'Add new account code set'")

    # Wait for navigation to the account code set form URL.
    page.wait_for_url("**/account_code_set_form/**", timeout=30000)


def open_account_code_set_form(page: Page, account_set_name: str) -> str:
    """Decide whether to skip (already saved) or start a fresh form.

    Returns "skip" when an existing row is found, otherwise "add".
    """

    print(f"- Checking if Account Code Set '{account_set_name}' already exists...")
    rows = page.locator("table tr").filter(has_text=account_set_name)
    try:
        exists = rows.count() > 0
    except Exception:
        exists = False

    if exists:
        print("  ✓ Existing entry already saved; skipping property.")
        return "skip"

    print("  → No existing entry; switching to Add new.")
    click_add_new_account_code_set(page)
    return "add"


def fill_account_code_set_name(page: Page, account_set_name: str) -> None:
    # The first visible text input on the form should be the Account Code Set Name.
    name_input = page.locator("input[type='text']").first
    current_value = ""
    try:
        current_value = name_input.input_value().strip()
    except Exception:
        pass

    if current_value:
        print(f"- Account Code Set Name already populated ({current_value!r}); leaving as-is.")
        return

    print(f"- Typing Account Code Set Name*: {account_set_name!r}")
    name_input.fill(account_set_name)


def facility_selection_present(page: Page) -> bool:
    combo = page.locator("#super-facility-selector")
    if combo.count() == 0:
        return False

    combo = combo.first
    try:
        return bool(
            combo.evaluate(
                """
                (el) => {
                    if (!el) return false;
                    const root = el.closest('div');
                    const findTextMatch = (nodeList) => {
                        for (const node of nodeList || []) {
                            if (node && node.textContent && node.textContent.trim().length > 0) {
                                return true;
                            }
                        }
                        return false;
                    };
                    const multi = root?.querySelectorAll('[class*="multiValue__label"]');
                    if (findTextMatch(multi)) return true;
                    const single = root?.querySelectorAll('[class*="singleValue"]');
                    if (findTextMatch(single)) return true;
                    return !!el.value?.trim();
                }
                """
            )
        )
    except Exception:
        pass

    try:
        return bool(combo.input_value().strip())
    except Exception:
        return False


def select_facility(page: Page, facility_search: str) -> bool:
    """Type into Facilities / Groups and select a unique facility if possible.

    Returns True if a single facility option was found and clicked, else False.
    """
    if facility_selection_present(page):
        print("- Facilities / Groups already populated; skipping selection.")
        return True

    print(f"- Selecting facility via Facilities / Groups using search: {facility_search!r}")
    if not facility_search:
        print("  ⚠️ No facility search text and no existing selection; skipping facility selection.")
        return False

    # The facilities selector uses a React-style combobox with an input that has
    # id="super-facility-selector" and a visible placeholder
    # "Select Facility / Facility Groups".
    try:
        placeholder = page.get_by_text("Select Facility / Facility Groups", exact=False)
        placeholder.click()
    except Exception:
        pass

    combo = page.locator("#super-facility-selector")
    if combo.count() == 0:
        print("  ⚠️ Could not locate super-facility selector input; skipping.")
        return False

    combo = combo.first

    # Clear any existing text and type slowly so the dropdown can filter.
    combo.fill("")
    combo.type(facility_search, delay=150)

    # Give the dropdown a moment to update.
    page.wait_for_timeout(800)

    # Try to find options matching the full facility name exactly.
    options = page.get_by_text(facility_search, exact=True)
    try:
        count = options.count()
    except Exception:
        count = 0

    print(f"  → Facility options matching search: {count}")

    if count == 0:
        print("  ⚠️ No facility options appeared after typing; will cancel this property.")
        return False

    if count > 1:
        print("  ⚠️ Multiple facilities visible; selecting the first one per instructions.")

    option = options.first
    try:
        option.scroll_into_view_if_needed()
        option.click(timeout=5000)
        print("  ✓ Facility selected via click")
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ Option click failed ({exc}); pressing Enter to accept first option.")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
    
    return True


def build_internal_code_row_map(page: Page) -> Dict[str, "Locator"]:
    """Build a mapping of Internal Code text -> row locator for the mapping table."""
    table = page.locator("table").filter(has_text="Internal Code").first
    body_rows = table.locator("tbody tr")
    row_count = body_rows.count()
    print(f"- Located mapping table with {row_count} body row(s).")

    mapping: Dict[str, Locator] = {}
    for i in range(row_count):
        row = body_rows.nth(i)
        # Assume the first cell holds the Internal Code.
        internal_text = row.locator("td").nth(0).inner_text().strip()
        if internal_text:
            mapping[internal_text] = row

    return mapping


def type_codes_into_table(page: Page, rows: List[AccountCodeRow]) -> None:
    """Type Code values into the Code column for matching Internal Codes."""
    mapping = build_internal_code_row_map(page)

    updated = 0
    skipped_missing_ui = 0
    skipped_empty_code = 0

    for r in rows:
        if not r.code:
            skipped_empty_code += 1
            continue
        ui_row = mapping.get(r.internal_code)
        if ui_row is None:
            skipped_missing_ui += 1
            continue

        # Assume the last input in the row is the Code field.
        inputs = ui_row.locator("input")
        if inputs.count() == 0:
            skipped_missing_ui += 1
            continue

        code_input = inputs.nth(inputs.count() - 1)
        print(f"  - Setting Code for Internal {r.internal_code}: {r.code}")
        code_input.fill(r.code)
        updated += 1

    print(f"- Code typing summary: updated={updated}, missing_ui_rows={skipped_missing_ui}, empty_code_rows={skipped_empty_code}")


def cancel_form(page: Page) -> None:
    """Click Cancel to discard changes and return to the list page."""
    print("- Clicking Cancel (DRY-RUN: do not save).")
    try:
        page.get_by_role("button", name="Cancel").click()
    except Exception:
        page.get_by_text("Cancel", exact=False).click()

    # Small pause to allow navigation back to the list.
    page.wait_for_timeout(1000)
    print("  ⏸ Waiting 10s to let StorEdge sync after Cancel ...")
    page.wait_for_timeout(10000)


def save_form(page: Page) -> None:
    """Click Save to persist changes and return to the list page."""
    print("- Scrolling to top and clicking Save (REAL RUN).")
    page.evaluate("window.scrollTo(0, 0)")
    save_button = page.get_by_role("button", name="Save").first
    save_button.scroll_into_view_if_needed()
    save_button.click()
    page.wait_for_url("**/account_code_sets", timeout=30000)
    page.wait_for_timeout(1000)
    print("  ⏸ Waiting 10s to let StorEdge sync after Save ...")
    page.wait_for_timeout(10000)


def submit_form(page: Page, *, dry_run: bool) -> None:
    if dry_run:
        cancel_form(page)
        print("\nDRY-RUN RESULT: Typed values then cancelled (no save).")
    else:
        save_form(page)
        print("\nREAL RUN RESULT: Form saved and returned to Account Code Sets list.")


def process_single_property(
    page: Page,
    sheet_title: str,
    account_set_name: str,
    rows: Sequence[AccountCodeRow],
    *,
    dry_run: bool,
) -> None:
    print("\n" + "=" * 80)
    run_mode_label = "DRY RUN" if dry_run else "REAL RUN"
    print(f"{run_mode_label}: {sheet_title} mapping from Sheet vs StorEdge UI")
    print("=" * 80)

    facility_search = extract_facility_search_text(account_set_name)

    print(f"Loaded from sheet tab '{sheet_title}':")
    print(f"- Account Code Set Name (H2): {account_set_name!r}")
    print(f"- Facility search text (prefix before ' -'): {facility_search!r}")
    print(f"- Data rows (A:E, non-empty): {len(rows)}")

    mode = open_account_code_set_form(page, account_set_name)
    if mode == "skip":
        print("RESULT: Account Code Set already saved; skipping this property.")
        return

    print("  ⏳ New form opened; pausing 5s before typing ...")
    page.wait_for_timeout(5000)
    fill_account_code_set_name(page, account_set_name)

    facility_ok = select_facility(page, facility_search)
    if not facility_ok:
        cancel_form(page)
        print("\nRESULT: Facility not found; form cancelled with no codes typed.")
        return

    type_codes_into_table(page, rows)
    submit_form(page, dry_run=dry_run)
    final_status = "cancelled" if dry_run else "saved"
    print(f"RESULT: Account Code Set add flow completed and {final_status}.")


def get_property_tab_names(sh: gspread.Spreadsheet) -> List[str]:
    titles: List[str] = []
    for ws in sh.worksheets():
        title = ws.title
        hidden = bool(ws._properties.get("hidden"))
        if title in GLOBAL_TABS or title in ALWAYS_SKIP_TABS or hidden:
            if hidden:
                print(f"- Skipping hidden sheet: {title}")
            continue
        titles.append(title)
    return titles


def process_all_properties(page: Page, sh: gspread.Spreadsheet, *, dry_run: bool) -> None:
    property_tabs = get_property_tab_names(sh)
    total = len(property_tabs)
    print(f"\nFound {total} property tabs to process (skipping {', '.join(sorted(ALWAYS_SKIP_TABS))}).")

    for idx, tab_name in enumerate(property_tabs, start=1):
        banner = f"[{idx}/{total}] {tab_name}"
        print("\n" + "=" * 80)
        print(banner)
        print("=" * 80)
        try:
            account_set_name, rows = load_property_mapping(sh, tab_name)
            process_single_property(
                page,
                tab_name,
                account_set_name,
                rows,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error while processing {tab_name}: {exc}")
            print("   Continuing with next property...")
            # Try to navigate back to the list page before continuing.
            try:
                page.wait_for_url("**/account_code_sets**", timeout=5000)
            except Exception:
                pass


def main() -> None:
    print("=" * 80)
    print("StorEdge Account Code Set automation")
    print("=" * 80)

    port = ask_debug_port()

    pw: Optional[Playwright] = None
    try:
        sh = connect_sheet()
        browser, page, pw = attach_browser(port)
        process_all_properties(page, sh, dry_run=DRY_RUN)
        print("\n✅ Automation run complete. Browser session remains open.")
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Error during automation: {exc}")
    finally:
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
