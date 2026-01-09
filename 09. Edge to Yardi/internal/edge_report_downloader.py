"""Edge GL Report Downloader.

Automates downloading General Ledger by Day reports from StorEdge for each facility.

Key capabilities:
- Attaches to an already-open Chrome via CDP (remote debugging port 9222).
- Reads facility order from facility_order.json.
- For each facility: switches facility, navigates to report, downloads CSV.
- Renames downloaded files to consistent naming convention.
- Records results to a match report JSON.

Usage:
    python edge_report_downloader.py --month "12. Dec" --start-date 12-01-2025 --end-date 12-31-2025
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from playwright.sync_api import Browser, Page, Playwright, sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================================================
# CONFIGURATION
# ============================================================================

DEBUG = False
CDP_PORT = 9222
STEP_DELAY_MS = 800
TYPING_DELAY_MS = 150
DOWNLOAD_TIMEOUT_S = 60
POST_FACILITY_SWITCH_WAIT_MS = 3000  # Wait for facility to fully load
POST_ACTION_WAIT_MS = 1000
POST_REPORTS_CLICK_WAIT_MS = 2000  # Wait for Reports page to load

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FACILITY_ORDER_PATH = PROJECT_ROOT.parent / ".helper_artifacts" / "09. Edge to Yardi" / "facility_order" / "facility_order.json"


def debug_print(msg: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {msg}")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FacilityRow:
    order: int
    property_code: str
    assignee: str
    property_name: str
    facility_hint: str
    match_method: str
    match_score: float


@dataclass
class DownloadResult:
    property_code: str
    facility_hint: str
    status: str  # "success", "skipped", "error"
    matched_facility: Optional[str] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MatchReport:
    report_month: str
    start_date: str
    end_date: str
    started_at: str
    ended_at: Optional[str] = None
    status: str = "IN_PROGRESS"
    target_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    cdp_endpoint: str = ""
    results: List[DownloadResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_month": self.report_month,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "run": {
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "cdp_endpoint_used": self.cdp_endpoint,
            },
            "status": self.status,
            "target_count": self.target_count,
            "success_count": self.success_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "results": [
                {
                    "property_code": r.property_code,
                    "facility_hint": r.facility_hint,
                    "status": r.status,
                    "matched_facility": r.matched_facility,
                    "file_path": r.file_path,
                    "error_message": r.error_message,
                    "timestamp": r.timestamp,
                }
                for r in self.results
            ],
            "errors": self.errors,
        }


# ============================================================================
# BROWSER ATTACHMENT
# ============================================================================

def attach_browser(port: int = CDP_PORT) -> Tuple[Browser, Page, Any, Playwright]:
    """Attach to existing Chrome and pick the StorEdge page.

    Returns (browser, page, context, playwright_instance).
    Caller is responsible for pw.stop(), but should NOT close the real browser.
    """
    pw = sync_playwright().start()
    endpoint = f"http://localhost:{port}"
    print(f"Connecting to existing Chrome via CDP at {endpoint} ...")
    
    try:
        browser = pw.chromium.connect_over_cdp(endpoint)
    except Exception as e:
        pw.stop()
        raise RuntimeError(
            f"Could not connect to Chrome at {endpoint}. "
            f"Make sure Chrome is running with --remote-debugging-port={port}"
        ) from e

    storedge_page: Optional[Page] = None
    storedge_context = None
    for context in browser.contexts:
        for page in context.pages:
            url = page.url.lower()
            title = (page.title() or "").lower()
            if "storedge" in url or "storable" in url or "edge" in title:
                storedge_page = page
                storedge_context = context
                break
        if storedge_page is not None:
            break

    if storedge_page is None:
        print("⚠️ Could not uniquely identify StorEdge tab; using first available page.")
        if browser.contexts and browser.contexts[0].pages:
            storedge_page = browser.contexts[0].pages[0]
            storedge_context = browser.contexts[0]
        else:
            pw.stop()
            raise RuntimeError("No pages found in browser.")

    print(f"Attached to page: '{storedge_page.title()}' -> {storedge_page.url}")
    return browser, storedge_page, storedge_context, pw


# ============================================================================
# FACILITY ORDER LOADING
# ============================================================================

def load_facility_order(path: Path = FACILITY_ORDER_PATH) -> List[FacilityRow]:
    """Load facility order from JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Facility order file not found: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    rows = []
    for row in data.get("rows", []):
        rows.append(FacilityRow(
            order=row.get("order", 0),
            property_code=row.get("property_code", ""),
            assignee=row.get("assignee", ""),
            property_name=row.get("property_name", ""),
            facility_hint=row.get("facility_hint", ""),
            match_method=row.get("match_method", ""),
            match_score=row.get("match_score", 0.0),
        ))
    
    # Sort by order
    rows.sort(key=lambda r: r.order)
    return rows


# ============================================================================
# UI INTERACTIONS
# ============================================================================

def parse_facility_names(facility_hint: str) -> List[str]:
    """Parse facility_hint into list of names to try.
    
    e.g., "Huntley North; HSS" -> ["Huntley North", "HSS"]
    e.g., "Candler" -> ["Candler"]
    """
    names = [name.strip() for name in facility_hint.split(";")]
    return [n for n in names if n]  # Filter empty strings


def open_facility_switcher_and_search(page: Page, facility_hint: str) -> Tuple[bool, Optional[str]]:
    """Open facility switcher and search for facility.
    
    The switcher button IS the search modal - type immediately after clicking.
    Tries each name from facility_hint (split by ;) until one matches.
    
    Returns (success, matched_facility_name).
    """
    names_to_try = parse_facility_names(facility_hint)
    debug_print(f"Names to try: {names_to_try}")
    
    for name in names_to_try:
        print(f"  Trying facility name: '{name}'")
        
        # Click the facility switcher button
        switcher_selectors = [
            "li.dropdown.facility-switcher > button",
            "#persistent-navbar li.dropdown.facility-switcher > button",
            "button:has-text('SWITCH FACILITY')",
        ]
        
        switcher_clicked = False
        for selector in switcher_selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=2000):
                    locator.click()
                    page.wait_for_timeout(STEP_DELAY_MS)
                    switcher_clicked = True
                    debug_print(f"Clicked facility switcher using: {selector}")
                    break
            except Exception as e:
                debug_print(f"Selector {selector} failed: {e}")
                continue
        
        if not switcher_clicked:
            print("  ⚠️ Could not find facility switcher button")
            return False, None
        
        # Wait for the modal to appear
        page.wait_for_timeout(500)
        
        # The facility switcher modal has its own input - we need to target it specifically
        # The modal appears on the right side after clicking "SWITCH FACILITY"
        # Look for input inside the facility switcher dropdown/modal
        switcher_input_selectors = [
            "li.dropdown.facility-switcher input[type='text']",
            "li.dropdown.facility-switcher input",
            ".facility-switcher input[type='text']",
            ".dropdown.open input[type='text']",
            "ul.dropdown-menu.open input",
        ]
        
        input_focused = False
        for selector in switcher_input_selectors:
            try:
                inp = page.locator(selector).first
                if inp.is_visible(timeout=1000):
                    inp.click()
                    input_focused = True
                    debug_print(f"Clicked facility switcher input using: {selector}")
                    break
            except Exception:
                continue
        
        if not input_focused:
            # Fallback: just start typing, the switcher should be focused
            debug_print("Could not find facility input, typing directly")
        
        # Clear any existing text - triple-click to select all, then delete
        page.keyboard.press("Control+a")
        page.wait_for_timeout(50)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(100)
        # Double-check it's clear
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(100)
        
        debug_print(f"Typing facility name: {name}")
        page.keyboard.type(name, delay=TYPING_DELAY_MS)
        page.wait_for_timeout(STEP_DELAY_MS)
        
        # Check if any facility options appeared
        facility_option_selectors = [
            "li.facility-item > a",
            ".facility-item",
        ]
        
        found_option = False
        for selector in facility_option_selectors:
            try:
                options = page.locator(selector)
                count = options.count()
                if count > 0:
                    found_option = True
                    debug_print(f"Found {count} facility option(s) with selector: {selector}")
                    break
            except Exception:
                continue
        
        if found_option:
            # Capture current URL before pressing Enter
            url_before = page.url
            
            # Press Enter to select
            print(f"  ✓ Found match for '{name}', pressing Enter...")
            page.keyboard.press("Enter")
            page.wait_for_timeout(POST_FACILITY_SWITCH_WAIT_MS)
            
            # Check if page actually changed (URL should be different after facility switch)
            url_after = page.url
            if url_before == url_after:
                # Page didn't change - facility switch didn't work
                print(f"  ⚠️ Page didn't reload after selecting '{name}' - switch may have failed")
                # Close the modal completely before trying next name
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                # Click somewhere neutral to dismiss any residual UI
                try:
                    page.locator("body").click(position={"x": 10, "y": 10})
                except Exception:
                    pass
                page.wait_for_timeout(500)
                continue
            
            debug_print(f"URL changed from {url_before} to {url_after}")
            return True, name
        else:
            # No match - clear and try next name
            debug_print(f"No match for '{name}', clearing and trying next...")
            # Clear the search input - select all and delete
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(300)
            # Close the switcher to reset
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
    
    # None of the names matched
    print(f"  ⚠️ No facility matched any of: {names_to_try}")
    return False, None


def navigate_to_report(page: Page) -> bool:
    """Navigate to Reports > Financial > General Ledger by Day."""
    print("  Navigating to General Ledger by Day report...")
    
    # Step 1: Click Reports in sidebar
    # First, ensure the page is ready (sometimes we're on dashboard after facility switch)
    page.wait_for_timeout(1000)  # Let the page stabilize
    
    reports_selectors = [
        "a:has-text('Reports')",
        "#main-navbar a:has-text('Reports')",
        "text=REPORTS",
    ]
    
    reports_clicked = False
    for selector in reports_selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=5000):
                locator.click()
                reports_clicked = True
                debug_print(f"Clicked Reports using: {selector}")
                break
        except Exception as e:
            debug_print(f"Reports selector {selector} failed: {e}")
            continue
    
    if not reports_clicked:
        print("  ⚠️ Could not click Reports link")
        return False
    
    # Wait for the Reports page to fully load
    # Wait for URL to contain "reports" OR wait for "EDGE Reports" text to appear
    print("  Waiting for Reports page to load...")
    try:
        page.wait_for_url("**/reports**", timeout=10000)
        debug_print("Reports URL detected")
    except Exception:
        debug_print("URL wait timed out, continuing anyway...")
    
    # Also wait for the EDGE Reports section to be visible - this is key
    # This ensures the page has actually loaded the reports content
    try:
        page.get_by_text("EDGE Reports").wait_for(state="visible", timeout=10000)
        debug_print("EDGE Reports section visible")
    except Exception as e:
        debug_print(f"EDGE Reports text not found: {e}")
        # Let's see what's on the page
        current_url = page.url
        debug_print(f"Current URL: {current_url}")
        if "/reports" not in current_url:
            print("  ⚠️ Not on Reports page")
            return False
        # If we're on reports URL but text isn't found, wait and retry
        page.wait_for_timeout(2000)
    
    # Extra safety wait for page stability
    page.wait_for_timeout(500)
    
    # Step 2: Click Financial section (expandable accordion)
    
    financial_clicked = False
    
    # Try multiple approaches to click Financial
    try:
        # Approach 1: Get all elements with "Financial" text and click the one in EDGE Reports section
        financial_els = page.get_by_text("Financial", exact=True)
        count = financial_els.count()
        debug_print(f"Found {count} elements with text 'Financial'")
        
        if count > 0:
            # Click the first one (should be in EDGE Reports)
            financial_els.first.click()
            page.wait_for_timeout(STEP_DELAY_MS)
            financial_clicked = True
            debug_print("Clicked Financial using get_by_text")
    except Exception as e:
        debug_print(f"get_by_text approach failed: {e}")
    
    if not financial_clicked:
        # Approach 2: Use XPath
        try:
            locator = page.locator("xpath=/html/body/div[2]/div/div/main/div[2]/div[1]/div[3]/div[1]")
            if locator.is_visible(timeout=2000):
                locator.click()
                page.wait_for_timeout(STEP_DELAY_MS)
                financial_clicked = True
                debug_print("Clicked Financial using XPath")
        except Exception as e:
            debug_print(f"XPath approach failed: {e}")
    
    if not financial_clicked:
        # Approach 3: Look for div containing "Financial" under EDGE Reports
        try:
            locator = page.locator("div:has-text('EDGE Reports') >> div:has-text('Financial')").first
            if locator.is_visible(timeout=2000):
                locator.click()
                page.wait_for_timeout(STEP_DELAY_MS)
                financial_clicked = True
                debug_print("Clicked Financial using EDGE Reports context")
        except Exception as e:
            debug_print(f"EDGE Reports context approach failed: {e}")
    
    if not financial_clicked:
        print("  ⚠️ Could not click Financial section")
        return False
    
    # Wait for the accordion to expand
    print("  Waiting for Financial section to expand...")
    page.wait_for_timeout(1000)
    
    # Step 3: Click General Ledger by Day
    gl_selectors = [
        "label:has-text('General Ledger by Day')",
        "text=General Ledger by Day",
        "xpath=/html/body/div[2]/div/div/main/div[2]/div[1]/div[3]/div[1]/div[2]/ul/li[13]/div/label",
    ]
    
    gl_clicked = False
    for selector in gl_selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=3000):
                locator.scroll_into_view_if_needed()
                locator.click()
                page.wait_for_timeout(POST_ACTION_WAIT_MS)
                gl_clicked = True
                debug_print(f"Clicked GL by Day using: {selector}")
                break
        except Exception as e:
            debug_print(f"GL selector {selector} failed: {e}")
            continue
    
    if not gl_clicked:
        print("  ⚠️ Could not click General Ledger by Day")
        return False
    
    return True


def fill_report_parameters(page: Page, start_date: str, end_date: str) -> bool:
    """Fill in the report parameters (dates and format)."""
    print(f"  Filling report parameters: {start_date} to {end_date}")
    
    # First, scroll to the TOP of the page to see the date inputs
    # The date inputs are at the top of the Financial section, above the report list
    print("  Scrolling to date inputs...")
    page.evaluate("window.scrollTo(0, 0)")  # Scroll to top of page
    page.wait_for_timeout(500)
    
    # The date inputs have placeholder "mm-dd-yyyy"
    # There are MANY hidden ones (one per report type) - we need the VISIBLE ones
    # Filter to only visible inputs
    date_inputs = page.locator("input[placeholder='mm-dd-yyyy']:visible")
    
    try:
        input_count = date_inputs.count()
        debug_print(f"Found {input_count} VISIBLE date input(s) with placeholder 'mm-dd-yyyy'")
    except Exception as e:
        debug_print(f"Could not count date inputs: {e}")
        input_count = 0
    
    if input_count < 2:
        # Try alternative - get all inputs and filter manually
        print("  Looking for visible date inputs manually...")
        all_date_inputs = page.locator("input[placeholder='mm-dd-yyyy']")
        total_count = all_date_inputs.count()
        debug_print(f"Total date inputs (including hidden): {total_count}")
        
        visible_inputs = []
        for i in range(min(total_count, 20)):  # Check first 20 at most
            try:
                inp = all_date_inputs.nth(i)
                if inp.is_visible():
                    visible_inputs.append(inp)
                    if len(visible_inputs) >= 2:
                        break
            except Exception:
                continue
        
        debug_print(f"Found {len(visible_inputs)} visible inputs by manual check")
        
        if len(visible_inputs) >= 2:
            try:
                start_input = visible_inputs[0]
                start_input.click()
                # Clear any existing text
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                page.wait_for_timeout(100)
                # Type slowly with delay, like facility name
                start_input.type(start_date, delay=TYPING_DELAY_MS)
                # Dispatch change event to trigger JS update
                start_input.dispatch_event("change")
                page.keyboard.press("Tab")  # Commit the value
                page.wait_for_timeout(300)
                debug_print(f"Filled start date: {start_date}")
                
                end_input = visible_inputs[1]
                end_input.click()
                # Clear any existing text
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                page.wait_for_timeout(100)
                end_input.type(end_date, delay=TYPING_DELAY_MS)
                # Dispatch change event to trigger JS update
                end_input.dispatch_event("change")
                page.keyboard.press("Tab")  # Commit the value
                page.wait_for_timeout(300)
                debug_print(f"Filled end date: {end_date}")
            except Exception as e:
                print(f"  ⚠️ Error filling date inputs: {e}")
                return False
        else:
            print("  ⚠️ Could not find 2 visible date inputs")
            return False
    else:
        # Use the visible mm-dd-yyyy placeholder inputs (first = start, second = end)
        try:
            start_input = date_inputs.nth(0)
            start_input.click()
            # Clear any existing text
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.wait_for_timeout(100)
            # Type slowly with delay, like facility name
            start_input.type(start_date, delay=TYPING_DELAY_MS)
            # Dispatch change event to trigger JS update
            start_input.dispatch_event("change")
            page.keyboard.press("Tab")  # Commit the value
            page.wait_for_timeout(300)
            debug_print(f"Filled start date: {start_date}")
            
            end_input = date_inputs.nth(1)
            end_input.click()
            # Clear any existing text
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.wait_for_timeout(100)
            end_input.type(end_date, delay=TYPING_DELAY_MS)
            # Dispatch change event to trigger JS update
            end_input.dispatch_event("change")
            page.keyboard.press("Tab")  # Commit the value
            page.wait_for_timeout(300)
            debug_print(f"Filled end date: {end_date}")
        except Exception as e:
            print(f"  ⚠️ Error filling date inputs: {e}")
            return False
    
    # Format dropdown - select Yardi (CSV)
    # The dropdown shows "Print (PDF)" by default
    # We need to target the VISIBLE format dropdown (only one should be visible at a time)
    try:
        # Get only the visible format dropdown
        format_select = page.locator("#format:visible").first
        
        # Click to open the dropdown
        format_select.click()
        page.wait_for_timeout(500)
        debug_print("Opened format dropdown")
        
        # Now select Yardi (CSV) using keyboard navigation
        # Arrow down to get to Yardi (CSV) - it's the last option
        for _ in range(7):  # There are about 7 options, Yardi is last
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(50)
        
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        debug_print("Selected Yardi (CSV) using keyboard navigation")
        
    except Exception as e:
        print(f"  ⚠️ Could not set format to Yardi (CSV): {e}")
    
    # Wait for the form to fully update after format selection
    print("  Waiting for form to update...")
    page.wait_for_timeout(3000)
    
    # Get the Generate Report link href and return it for navigation
    # The Tab+Enter approach doesn't work - we need to get the actual URL
    try:
        generate_link = page.locator("div.report-form-container.general-ledger-by-day a.report-link")
        if generate_link.is_visible(timeout=2000):
            href = generate_link.get_attribute("href")
            debug_print(f"Generate Report href: {href}")
            # Store the href to use for download
            page.evaluate(f"window.__report_href = '{href}'")
        else:
            debug_print("Could not find Generate Report link to get href")
    except Exception as e:
        debug_print(f"Error getting Generate Report href: {e}")
    
    page.wait_for_timeout(STEP_DELAY_MS)
    return True


def generate_and_download(page: Page, context, download_dir: Path, property_code: str, report_month: str, start_date: str, end_date: str) -> Tuple[bool, Optional[Path]]:
    """Download the report using requests with browser cookies.
    
    Returns (success, downloaded_file_path).
    """
    print("  Downloading report...")
    
    # Parse our dates (format: mm-dd-yyyy) and convert to URL format (YYYY-M-D)
    try:
        start_parts = start_date.split("-")  # mm-dd-yyyy
        end_parts = end_date.split("-")
        
        start_url = f"{start_parts[2]}-{int(start_parts[0])}-{int(start_parts[1])}"  # YYYY-M-D
        end_url = f"{end_parts[2]}-{int(end_parts[0])}-{int(end_parts[1])}"
        
        debug_print(f"Date URL format: {start_url} to {end_url}")
    except Exception as e:
        print(f"  ⚠️ Error parsing dates: {e}")
        return False, None
    
    # Extract company and facility IDs from current URL
    current_url = page.url
    try:
        match = re.search(r'/company/(\d+)/facility/(\d+)', current_url)
        if match:
            company_id = match.group(1)
            facility_id = match.group(2)
        else:
            print("  ⚠️ Could not extract company/facility IDs from URL")
            return False, None
    except Exception as e:
        print(f"  ⚠️ Error extracting IDs: {e}")
        return False, None
    
    # Build the full URL
    base_url = "https://www.storedgefms.com"
    full_url = f"{base_url}/company/{company_id}/facility/{facility_id}/reports/general_ledger_by_day/{start_url}/{end_url}.csv?export=yardi"
    
    debug_print(f"Report URL: {full_url}")
    
    # Get cookies from the browser context
    cookies = context.cookies()
    cookie_dict = {c['name']: c['value'] for c in cookies}
    debug_print(f"Got {len(cookie_dict)} cookies from browser")
    
    # Use requests to download the file
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(full_url, cookies=cookie_dict, headers=headers, timeout=60)
        debug_print(f"Response status: {response.status_code}, size: {len(response.content)} bytes")
        
        if response.status_code == 200 and len(response.content) > 100:
            # Save the file
            download_dir.mkdir(parents=True, exist_ok=True)
            target_filename = f"edge_gl_by_day__{property_code}__{report_month}.csv"
            target_path = download_dir / target_filename
            
            with open(target_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✓ Downloaded: {target_filename} ({len(response.content):,} bytes)")
            return True, target_path
        else:
            print(f"  ⚠️ Download failed - status: {response.status_code}, size: {len(response.content)}")
            return False, None
            
    except Exception as e:
        print(f"  ⚠️ Request error: {e}")
        return False, None


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def run_download_workflow(
    month_folder: str,
    start_date: str,
    end_date: str,
    assignee_filter: Optional[str] = None,
    start_index: int = 1,
) -> MatchReport:
    """Run the full download workflow for all facilities."""
    
    # Parse report month from date (e.g., "12-01-2025" -> "2025-12")
    parts = start_date.split("-")
    if len(parts) == 3:
        report_month = f"{parts[2]}-{parts[0]}"
    else:
        report_month = start_date
    
    # Set up paths
    output_dir = PROJECT_ROOT / month_folder / "Output" / "edge_downloads"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    match_report_path = output_dir / f"edge_download_match_report__{report_month}.json"
    
    # Initialize report
    report = MatchReport(
        report_month=report_month,
        start_date=start_date,
        end_date=end_date,
        started_at=datetime.now().isoformat(),
        cdp_endpoint=f"http://localhost:{CDP_PORT}",
    )
    
    # Load facility order
    print("\n=== Loading facility order ===")
    try:
        facilities = load_facility_order()
        print(f"Loaded {len(facilities)} facilities from facility_order.json")
    except Exception as e:
        report.status = "FAILED"
        report.errors.append(f"Failed to load facility order: {e}")
        report.ended_at = datetime.now().isoformat()
        return report
    
    # Filter by assignee if specified
    if assignee_filter:
        facilities = [f for f in facilities if f.assignee.lower() == assignee_filter.lower()]
        print(f"Filtered to {len(facilities)} facilities for assignee: {assignee_filter}")
    
    report.target_count = len(facilities)
    
    # Connect to browser
    print("\n=== Connecting to browser ===")
    pw: Optional[Playwright] = None
    context = None
    try:
        browser, page, context, pw = attach_browser(CDP_PORT)
    except Exception as e:
        report.status = "FAILED"
        report.errors.append(str(e))
        report.ended_at = datetime.now().isoformat()
        # _save_report(report, match_report_path)  # Skip JSON report
        return report
    
    try:
        # Process each facility
        print(f"\n=== Processing {len(facilities)} facilities ===\n")
        
        for i, facility in enumerate(facilities, 1):
            # Skip facilities before start_index
            if i < start_index:
                continue
            
            print(f"\n[{i}/{len(facilities)}] {facility.property_code} - {facility.facility_hint}")
            print("-" * 60)
            
            result = DownloadResult(
                property_code=facility.property_code,
                facility_hint=facility.facility_hint,
                status="pending",
            )
            
            try:
                # Step 1+2: Open facility switcher and search/select facility
                success, matched = open_facility_switcher_and_search(page, facility.facility_hint)
                if not success:
                    # This is the ONLY case where we skip to next facility
                    # (facility not found or page didn't change after selection)
                    result.status = "skipped"
                    result.error_message = f"Facility not found: {facility.facility_hint}"
                    report.skipped_count += 1
                    report.results.append(result)
                    continue
                
                result.matched_facility = matched
                
                # From here on, any failure should STOP the script, not continue
                # because we're now on the correct facility and need to complete the full process
                
                # Step 3: Navigate to report
                if not navigate_to_report(page):
                    result.status = "error"
                    result.error_message = "Could not navigate to report"
                    report.error_count += 1
                    report.results.append(result)
                    report.errors.append(f"STOPPED at {facility.property_code}: Could not navigate to report")
                    raise RuntimeError(f"Navigation failed for {facility.property_code} - stopping")
                
                # Step 4: Fill parameters
                if not fill_report_parameters(page, start_date, end_date):
                    result.status = "error"
                    result.error_message = "Could not fill report parameters"
                    report.error_count += 1
                    report.results.append(result)
                    report.errors.append(f"STOPPED at {facility.property_code}: Could not fill report parameters")
                    raise RuntimeError(f"Form fill failed for {facility.property_code} - stopping")
                
                # Step 5: Generate and download
                success, file_path = generate_and_download(
                    page, context, output_dir, facility.property_code, report_month, start_date, end_date
                )
                
                if success and file_path:
                    result.status = "success"
                    result.file_path = str(file_path)
                    report.success_count += 1
                    print(f"  ✓ SUCCESS: {file_path.name}")
                else:
                    result.status = "error"
                    result.error_message = "Download failed or timed out"
                    report.error_count += 1
                    report.results.append(result)
                    report.errors.append(f"STOPPED at {facility.property_code}: Download failed")
                    raise RuntimeError(f"Download failed for {facility.property_code} - stopping")
                
                report.results.append(result)
                
                # Save intermediate report
                # _save_report(report, match_report_path)  # Skip JSON report
                
            except PlaywrightTimeout as e:
                result.status = "error"
                result.error_message = f"Timeout: {e}"
                report.error_count += 1
                report.results.append(result)
                report.errors.append(f"{facility.property_code}: Timeout - {e}")
                # Re-raise to stop the loop
                raise
                
            except RuntimeError as e:
                # RuntimeError is raised intentionally to stop the loop - re-raise it
                raise
                
            except Exception as e:
                result.status = "error"
                result.error_message = str(e)
                report.error_count += 1
                report.results.append(result)
                report.errors.append(f"{facility.property_code}: {e}")
                print(f"  ⚠️ ERROR: {e}")
                # Re-raise to stop the loop
                raise
    
    finally:
        # Clean up playwright (but don't close the actual browser)
        if pw:
            pw.stop()
    
    # Finalize report
    report.ended_at = datetime.now().isoformat()
    if report.error_count == 0 and report.skipped_count == 0:
        report.status = "COMPLETED"
    elif report.success_count > 0:
        report.status = "PARTIAL"
    else:
        report.status = "FAILED"
    
    # _save_report(report, match_report_path)  # Skip JSON report
    
    return report


def _save_report(report: MatchReport, path: Path) -> None:
    """Save match report to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    debug_print(f"Saved report to {path}")


# ============================================================================
# CLI
# ============================================================================

def print_banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_summary(report: MatchReport) -> None:
    print("\n" + "=" * 70)
    print("  RUN SUMMARY")
    print("=" * 70)
    print(f"  Status:    {report.status}")
    print(f"  Target:    {report.target_count} facilities")
    print(f"  Success:   {report.success_count}")
    print(f"  Skipped:   {report.skipped_count}")
    print(f"  Errors:    {report.error_count}")
    print(f"  Started:   {report.started_at}")
    print(f"  Ended:     {report.ended_at}")
    print("=" * 70)
    print(f"FINAL_MARKER: {report.status}")


def main():
    global DEBUG, CDP_PORT
    
    parser = argparse.ArgumentParser(description="Download Edge GL reports for all facilities")
    parser.add_argument("--month", required=True, help="Month folder name (e.g., '12. Dec')")
    parser.add_argument("--start-date", required=True, help="Start date (mm-dd-yyyy)")
    parser.add_argument("--end-date", required=True, help="End date (mm-dd-yyyy)")
    parser.add_argument("--assignee", help="Filter to specific assignee (e.g., 'Jay')")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--port", type=int, default=9222, help="CDP port (default: 9222)")
    parser.add_argument("--start-index", type=int, default=1, help="Start from this facility index (1-based)")
    
    args = parser.parse_args()
    
    DEBUG = args.debug
    CDP_PORT = args.port
    
    print_banner(f"Edge GL Report Downloader - {args.month}")
    print(f"  Date range: {args.start_date} to {args.end_date}")
    if args.assignee:
        print(f"  Assignee filter: {args.assignee}")
    if args.start_index > 1:
        print(f"  Starting from facility index: {args.start_index}")
    print()
    
    report = run_download_workflow(
        month_folder=args.month,
        start_date=args.start_date,
        end_date=args.end_date,
        assignee_filter=args.assignee,
        start_index=args.start_index,
    )
    
    print_summary(report)


if __name__ == "__main__":
    main()
