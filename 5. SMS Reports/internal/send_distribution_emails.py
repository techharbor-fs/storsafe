"""Send monthly SMS financial + distribution reports via Gmail."""
from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

# Load .env from project root (Storsafe folder)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from generate_monthly_distribution_reports import (  # type: ignore
    PROPERTY_CONFIG,
    REPORTS_BASE,
    derive_property_config,
    get_available_months,
    iter_financial_workbooks,
    normalize_property_key,
    parse_folder_to_month,
)

BODY_TEMPLATE = """Hi Brian,

Please see attached.

<br>

<table cellspacing="0" cellpadding="0" style="box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0.75pt; height: 9pt;"></td>
</tr>
<tr>
<td style="padding: 0.75pt;">
<table cellspacing="0" cellpadding="0" style="box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0in 9pt 0in 0.75pt; vertical-align: top; width: 48.75pt;">
<p style="text-align: center; margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;">
<span style="font-family: Verdana, sans-serif; color: blue;"><u><a href="http://www.storsafe.com/" target="_blank" style="color: blue;"><img src="https://d36urhup7zbd7q.cloudfront.net/u/O6rPAd3ebQY/1685551571097.png" alt="StorSafe Logo" width="64" height="55" style="width: 0.677in; height: 0.5833in;"></a></u></span></p>
</td>
<td style="border-width: medium medium medium 1pt; border-style: none none none solid; border-color: currentcolor currentcolor currentcolor rgb(189, 189, 189); padding: 0in 0in 0in 9pt; vertical-align: top;">
<table cellspacing="0" cellpadding="0" style="box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0in;">
<p style="margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;"><span style="font-family: Verdana, sans-serif; font-size: 12pt; color: rgb(100, 100, 100);"><b>Jay Villasurda</b></span><span style="font-family: Verdana, sans-serif;"><br>
</span><span style="font-family: Verdana, sans-serif; font-size: 10pt; color: rgb(100, 100, 100);"><b>Senior Accountant - Remote</b></span></p>
</td>
</tr>
<tr>
<td style="padding: 0in;">
<table cellspacing="0" cellpadding="0" style="box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 9pt 0in 0in; width: 348.75pt;">
<p style="margin: 0.1pt; font-family: Calibri, sans-serif; font-size: 11pt;">
<span style="font-family: Verdana, sans-serif; font-size: 8.5pt; color: rgb(7, 55, 99);"><a href="https://api.whatsapp.com/send/?phone=639173341487" target="_blank" style="color: rgb(7, 55, 99); text-decoration: underline;">+63 917-334-1487</a></span>
</p>
<p style="margin: 0.1pt; font-family: Calibri, sans-serif; font-size: 11pt;">
<span style="font-family: Verdana, sans-serif; font-size: 8.5pt; color: rgb(7, 55, 99);"><a href="mailto:jvillasurda@storsafe.com" target="_blank" style="color: rgb(7, 55, 99); text-decoration: underline;">jvillasurda@storsafe.com</a></span>
</p>
<p style="margin: 0.1pt; font-family: Calibri, sans-serif; font-size: 11pt;">
<span style="font-family: Verdana, sans-serif; font-size: 8.5pt; color: rgb(7, 55, 99);"><a href="https://www.storsafe.com/" target="_blank" style="color: rgb(7, 55, 99); text-decoration: underline;">https://www.storsafe.com/</a></span>
</p>
</td>
</tr>
</tbody>
</table>
</td>
</tr>
</tbody>
</table>
</td>
</tr>
</tbody>
</table>
<p style="line-height: 0%; margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;">
&nbsp;</p>
<table cellspacing="0" cellpadding="0" style="width: 100%; box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0in; height: 12pt;"></td>
</tr>
</tbody>
</table>
<p style="line-height: 0%; margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;">
&nbsp;</p>
<table cellspacing="0" cellpadding="0" style="width: 6.25in; box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0in;">
<table cellspacing="0" cellpadding="0" style="width: 100%; box-sizing: border-box; border-collapse: collapse; border-spacing: 0px;">
<tbody>
<tr>
<td style="padding: 0in;">
<p style="margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;"><span style="color: rgb(0, 0, 0);"><u><a href="http://www.storsafe.com/" target="_blank" style="color: rgb(0, 0, 0);"><img src="https://d36urhup7zbd7q.cloudfront.net/u/O6rPAd3ebQY/1685545504802.png" alt="App Banner Image" width="294" height="69" style="width: 3.0625in; height: 0.7291in;"></a></u></span></p>
</td>
</tr>
</tbody>
</table>
</td>
</tr>
</tbody>
</table>
</td>
</tr>
<tr>
<td style="padding: 0.75pt;">
<p style="line-height: 0%; margin: 0in; font-family: Calibri, sans-serif; font-size: 11pt;">
<span style="font-family: &quot;ws-id qONXXPoJVPD&quot;; font-size: 1pt;">&nbsp;</span></p>
</td>
</tr>
</tbody>
</table>
"""

# Production recipients
RECIPIENTS: dict[str, dict[str, list[str]]] = {
    "altoona": {
        "to": ["spacemanagement1220@gmail.com"],
        "cc": ["ealbento@elmdalepartners.com", "pmenzel@elmdalepartners.com", "mclark@elmdalepartners.com", "lmcfarlane@elmdalepartners.com", "jvillasurda@storsafe.com"],
    },
    "cary": {
        "to": ["spacemanagement8405@gmail.com"],
        "cc": ["ealbento@elmdalepartners.com", "pmenzel@elmdalepartners.com", "mclark@elmdalepartners.com", "lmcfarlane@elmdalepartners.com", "jvillasurda@storsafe.com"],
    },
    "crystal lake": {
        "to": ["spacemanagement920@gmail.com"],
        "cc": ["ealbento@elmdalepartners.com", "pmenzel@elmdalepartners.com", "mclark@elmdalepartners.com", "lmcfarlane@elmdalepartners.com", "jvillasurda@storsafe.com"],
    },
    "nfss": {
        "to": ["spacemanagement542@gmail.com"],
        "cc": ["ealbento@elmdalepartners.com", "pmenzel@elmdalepartners.com", "mclark@elmdalepartners.com", "lmcfarlane@elmdalepartners.com", "jvillasurda@storsafe.com"],
    },
}


def load_credentials() -> tuple[str, str]:
    """Load email credentials from environment variables."""
    user = os.getenv("SMS_EMAIL_USER")
    password = os.getenv("SMS_EMAIL_PASS")
    
    if not user or not password:
        raise ValueError(
            "Email credentials not found. Set SMS_EMAIL_USER and SMS_EMAIL_PASS in .env file.\n"
            "Expected location: C:\\Users\\jvill\\techharbor-fs\\Storsafe\\.env"
        )
    
    return user, password


# --- Sent Log Functions (Duplicate Prevention) ---

SENT_LOG_FILENAME = ".email_sent_log.json"


def get_sent_log_path(reports_folder: Path) -> Path:
    """Get the path to the sent log file for a month folder."""
    return reports_folder / SENT_LOG_FILENAME


def load_sent_log(reports_folder: Path) -> dict:
    """Load the sent log for a month folder. Returns empty dict if not found."""
    log_path = get_sent_log_path(reports_folder)
    if log_path.exists():
        with open(log_path, "r") as f:
            return json.load(f)
    return {}


def save_sent_log(reports_folder: Path, log_data: dict) -> None:
    """Save the sent log for a month folder."""
    log_path = get_sent_log_path(reports_folder)
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)


def record_sent_email(reports_folder: Path, property_key: str, subject: str) -> None:
    """Record that an email was sent for a property."""
    log = load_sent_log(reports_folder)
    log[property_key] = {
        "subject": subject,
        "sent_at": datetime.now().isoformat(),
    }
    save_sent_log(reports_folder, log)


def check_already_sent(reports_folder: Path, jobs: list) -> list[tuple[str, str]]:
    """
    Check if any emails were already sent.
    Returns list of (property_name, sent_at) for properties that were already sent.
    """
    log = load_sent_log(reports_folder)
    already_sent = []
    for job in jobs:
        if job.property_key in log:
            sent_info = log[job.property_key]
            already_sent.append((job.property_name, sent_info.get("sent_at", "unknown")))
    return already_sent


@dataclass
class EmailJob:
    property_key: str
    property_name: str
    subject: str
    to_recipients: list[str]
    cc_recipients: list[str]
    attachments: list[Path]


def select_folder_interactive() -> tuple[Path, str] | None:
    """Present interactive menu to select a month folder. Returns (folder_path, report_month)."""
    folders = get_available_months()
    
    if not folders:
        print(f"No month folders found in {REPORTS_BASE}")
        return None
    
    print("\n=== Available Month Folders ===\n")
    for i, folder in enumerate(folders, 1):
        # Count financial and distribution workbooks
        fin_count = len(list(folder.glob("SMS-*Financial*.xlsx")))
        dist_count = len(list(folder.glob("*Distribution*.xlsx")))
        print(f"  {i}. {folder.name}  ({fin_count} Financial, {dist_count} Distribution)")
    
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
        description="Send SMS monthly reports via Outlook",
    )
    parser.add_argument(
        "--reports-folder",
        type=Path,
        help="Folder containing the month's workbooks. If not provided, shows interactive selection.",
    )
    parser.add_argument(
        "--report-month",
        help="Reporting month in YYYY-MM format. Auto-detected from folder name if not provided.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the emails via Outlook instead of running in dry-run mode",
    )
    return parser.parse_args()


def build_month_label(report_month: str) -> tuple[str, int, int]:
    year, month = map(int, report_month.split("-"))
    return f"{month:02d}.{year}", year, month


def map_financial_workbooks(reports_folder: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for workbook in iter_financial_workbooks(reports_folder):
        config = derive_property_config(workbook)
        key = normalize_property_key(config.property_name)
        mapping[key] = workbook
    return mapping


def expected_distribution_path(
    reports_folder: Path,
    month_label: str,
    property_key: str,
) -> Path:
    if property_key not in PROPERTY_CONFIG:
        raise KeyError(f"Unknown property key: {property_key}")
    config = PROPERTY_CONFIG[property_key]
    name = f"{month_label} SMS - {config.output_label} Distribution recommendation.xlsx"
    return reports_folder / name


def iter_email_jobs(
    reports_folder: Path,
    month_label: str,
    financial_map: dict[str, Path],
) -> Iterable[EmailJob]:
    for property_key, recipients in RECIPIENTS.items():
        if property_key not in PROPERTY_CONFIG:
            print(f"[WARN] Property key '{property_key}' missing from PROPERTY_CONFIG; skipping")
            continue
        config = PROPERTY_CONFIG[property_key]
        financial_path = financial_map.get(property_key)
        if not financial_path:
            print(f"[WARN] Missing financial workbook for {config.property_name}; skipping")
            continue
        distribution_path = expected_distribution_path(reports_folder, month_label, property_key)
        if not distribution_path.exists():
            print(f"[WARN] Missing distribution workbook: {distribution_path.name}; skipping")
            continue
        subject = f"{month_label} Financials - {config.property_name}"
        yield EmailJob(
            property_key=property_key,
            property_name=config.property_name,
            subject=subject,
            to_recipients=recipients["to"],
            cc_recipients=recipients.get("cc", []),
            attachments=[financial_path, distribution_path],
        )


def send_via_gmail(job: EmailJob, body: str, username: str, password: str) -> None:
    """Send email via Gmail SMTP with app password."""
    msg = EmailMessage()
    msg["From"] = username
    msg["To"] = ", ".join(job.to_recipients)
    msg["Cc"] = ", ".join(job.cc_recipients)
    msg["Subject"] = job.subject
    msg.set_content(body, subtype="html")

    for attachment in job.attachments:
        with open(attachment, "rb") as f:
            file_data = f.read()
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=attachment.name,
            )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)


def dry_run(job: EmailJob, body: str) -> None:
    print("--- DRY RUN ---")
    print(f"Subject : {job.subject}")
    print(f"To      : {', '.join(job.to_recipients)}")
    if job.cc_recipients:
        print(f"Cc      : {', '.join(job.cc_recipients)}")
    print("Attachments:")
    for attachment in job.attachments:
        print(f"  - {attachment.name}")
    print(body)


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

    month_label, _, _ = build_month_label(report_month_str)
    financial_map = map_financial_workbooks(reports_folder)
    jobs = list(iter_email_jobs(reports_folder, month_label, financial_map))

    if not jobs:
        print("No emails to process. Ensure financial and distribution workbooks exist.")
        return
    
    # Check for already-sent emails (duplicate prevention)
    already_sent = check_already_sent(reports_folder, jobs)
    
    # Show summary before sending
    print(f"\n=== Email Summary ({len(jobs)} emails) ===\n")
    for job in jobs:
        print(f"  {job.property_name}:")
        print(f"    To: {', '.join(job.to_recipients)}")
        print(f"    Attachments: {', '.join(a.name for a in job.attachments)}")
    print()
    
    # Warn if emails were already sent
    if already_sent:
        print("=" * 50)
        print("WARNING: Some emails were already sent!")
        print("=" * 50)
        for prop_name, sent_at in already_sent:
            # Format the timestamp nicely
            try:
                dt = datetime.fromisoformat(sent_at)
                formatted = dt.strftime("%Y-%m-%d %I:%M %p")
            except:
                formatted = sent_at
            print(f"  - {prop_name}: sent on {formatted}")
        print()
    
    # Determine send mode - CLI flag or interactive
    if args.send:
        should_send = True
        # If using --send flag and emails were already sent, require confirmation
        if already_sent:
            print("Use interactive mode to re-send (remove --send flag).")
            return
    else:
        print("What would you like to do?\n")
        print("  1. Dry run (preview only, no emails sent)")
        if already_sent:
            print("  2. Re-send emails (CAUTION: duplicates will be sent)")
        else:
            print("  2. Send emails")
        print("  0. Cancel\n")
        
        while True:
            choice = input("Select option: ").strip()
            if choice == "0" or choice.lower() == "q":
                print("Cancelled.")
                return
            elif choice == "1":
                should_send = False
                break
            elif choice == "2":
                if already_sent:
                    confirm = input("Type 'yes' to confirm re-sending: ").strip().lower()
                    if confirm != "yes":
                        print("Cancelled.")
                        return
                should_send = True
                break
            else:
                print("Please enter 0, 1, or 2")
    
    if should_send:
        username, password = load_credentials()
        print("\nSending emails...\n")
        
        for job in jobs:
            send_via_gmail(job, BODY_TEMPLATE, username, password)
            record_sent_email(reports_folder, job.property_key, job.subject)
            print(f"[SENT] {job.subject}")
        
        print(f"\n[OK] All {len(jobs)} emails sent successfully.")
    else:
        print("\n--- DRY RUN (No emails sent) ---\n")
        for job in jobs:
            print(f"Would send: {job.subject}")
            print(f"  To: {', '.join(job.to_recipients)}")
            if job.cc_recipients:
                print(f"  Cc: {', '.join(job.cc_recipients)}")
            print(f"  Attachments: {len(job.attachments)} files")
            print()


if __name__ == "__main__":
    main()
