# Best Practices for Production-Ready Automation

**Last Updated**: October 12, 2025
**Purpose**: Guidelines for implementing enterprise-grade automation scripts

---

## 📋 Table of Contents

1. [Error Handling & Retry Logic](#error-handling--retry-logic)
1. [Input Validation](#input-validation)
1. [Environment Variables](#environment-variables)
1. [Backup Strategy](#backup-strategy)
1. [Health Checks & Monitoring](#health-checks--monitoring)
1. [Performance Monitoring](#performance-monitoring)
1. [Code Documentation Standards](#code-documentation-standards)
1. [Dependency Management](#dependency-management)

---

## 1. Error Handling & Retry Logic

### Why It Matters (Error Handling & Retry Logic)

External APIs (Google Sheets, QuickBooks, Selenium) can fail temporarily due to:

- Network issues
- Rate limiting
- Service interruptions
- Timeout errors

### Implementation (Error Handling & Retry Logic)

**Install retry library:**

```bash
pip install tenacity
```

**Basic Retry Pattern:**

```python
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def call_google_sheets_api(sheet_id, range_name):
    """
    Call Google Sheets API with automatic retry on failure.

    Retries up to 3 times with exponential backoff:
    - Attempt 1: Immediate
    - Attempt 2: Wait 2 seconds
    - Attempt 3: Wait 4 seconds
    """
    try:
        logger.info(f"Fetching data from sheet: {sheet_id}")
        # Your API call here
        result = worksheet.get_all_records()
        return result
    except Exception as e:
        logger.warning(f"API call failed, will retry: {e}")
        raise  # Let tenacity handle the retry
```

### Advanced: Retry Specific Exceptions Only

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True
)
def call_quickbooks_api(endpoint, data):
    """Retry only on network issues, not validation errors"""
    response = requests.post(endpoint, json=data)
    response.raise_for_status()  # Don't retry 400/401 errors
    return response.json()
```

**When to Use:**

- ✅ Google Sheets API calls
- ✅ QuickBooks API calls
- ✅ Selenium web scraping (page load failures)
- ✅ File I/O over network drives
- ❌ User input validation (fail fast)
- ❌ Business logic errors (fix the code)

---

## 2. Input Validation

### Why It Matters (Input Validation)

Bad data causes:

- Partial processing (some records succeed, others fail)
- Incorrect calculations
- Silent failures
- Data corruption

### Implementation (Input Validation)

**Data Validation Template:**

```python
from typing import Dict, List, Any
import re
from datetime import datetime

class ValidationError(Exception):
    """Custom exception for validation failures"""
    pass

def validate_timesheet_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate timesheet data before processing.

    Args:
        entry: Dictionary containing timesheet data

    Returns:
        Validated entry (unchanged if valid)

    Raises:
        ValidationError: If validation fails with descriptive message
    """
    # Check required fields
    required_fields = ['employee_name', 'hours_worked', 'project_id', 'date']
    missing_fields = [f for f in required_fields if f not in entry]

    if missing_fields:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

    # Validate hours worked
    try:
        hours = float(entry['hours_worked'])
        if hours < 0:
            raise ValidationError(f"Hours cannot be negative: {hours}")
        if hours > 24:
            raise ValidationError(f"Hours cannot exceed 24 per day: {hours}")
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid hours format: {entry['hours_worked']}")

    # Validate project ID format (ABC-01-001)
    project_pattern = r'^[A-Z]{3}-\d{2}-\d{3}$'
    if not re.match(project_pattern, entry['project_id']):
        raise ValidationError(
            f"Invalid project ID format: {entry['project_id']} "
            f"(Expected: XXX-##-###)"
        )

    # Validate date
    try:
        datetime.strptime(entry['date'], '%Y-%m-%d')
    except ValueError:
        raise ValidationError(f"Invalid date format: {entry['date']} (Expected: YYYY-MM-DD)")

    return entry

def validate_invoice_data(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Validate invoice data before submission to QuickBooks"""

    # Check customer exists
    if not invoice.get('customer_name'):
        raise ValidationError("Customer name is required")

    # Validate line items
    if not invoice.get('line_items') or len(invoice['line_items']) == 0:
        raise ValidationError("Invoice must have at least one line item")

    total = 0.0
    for idx, item in enumerate(invoice['line_items']):
        # Check required fields
        if 'description' not in item:
            raise ValidationError(f"Line {idx + 1}: Missing description")

        if 'quantity' not in item or 'rate' not in item:
            raise ValidationError(f"Line {idx + 1}: Missing quantity or rate")

        # Validate amounts
        try:
            qty = float(item['quantity'])
            rate = float(item['rate'])

            if qty <= 0:
                raise ValidationError(f"Line {idx + 1}: Quantity must be positive")
            if rate < 0:
                raise ValidationError(f"Line {idx + 1}: Rate cannot be negative")

            total += qty * rate
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Line {idx + 1}: Invalid number format - {e}")

    # Sanity check: flag unusually large invoices
    if total > 100000:
        logger.warning(f"⚠️ Unusually large invoice: ${total:,.2f}")

    return invoice
```

**Usage in Scripts:**

```python
from logger_config import setup_logger

logger = setup_logger('payroll')

def process_timesheets(data):
    """Process timesheets with validation"""
    valid_entries = []
    errors = []

    for idx, entry in enumerate(data):
        try:
            validated = validate_timesheet_entry(entry)
            valid_entries.append(validated)
        except ValidationError as e:
            error_msg = f"Row {idx + 1}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Stop if too many errors
    error_rate = len(errors) / len(data) if data else 0
    if error_rate > 0.1:  # More than 10% errors
        raise ValueError(
            f"Too many validation errors ({len(errors)}/{len(data)}). "
            f"Please check input data."
        )

    logger.info(f"✅ Validated {len(valid_entries)} entries, {len(errors)} errors")
    return valid_entries, errors
```

---

## 3. Environment Variables

### Why It Matters (Environment Variables)

Hardcoded paths break when:

- Running on different machines
- Different users run the script
- OneDrive syncs to different locations
- Collaborating with others

### Implementation (Environment Variables)

**Install python-dotenv:**

```bash
pip install python-dotenv
```

**Create `.env` file (add to .gitignore!):**

```env
# .env - User-specific configuration (DO NOT COMMIT)

# OneDrive paths
ONEDRIVE_ROOT=C:\Users\jayry\OneDrive\OneDrive - WESTONS CORPORATION
TIMESHEETS_ROOT=${ONEDRIVE_ROOT}\Ben Price's files - WESTONS SAFETY STAFFING\Automation\01. Timesheets

# Google Sheets
MAIN_SHEET_ID=1v-UmAkTbuHsJa1V_6-bDJuLc1jv8ZnfiS2SxP-Q2Oec

# Development settings
DEBUG_MODE=True
DRY_RUN=False
```

**Update paths.py:**

```python
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Get paths from environment with fallbacks
ONEDRIVE_ROOT = os.getenv(
    'ONEDRIVE_ROOT',
    r'C:\Users\jayry\OneDrive\OneDrive - WESTONS CORPORATION'
)

TIMESHEETS_ROOT = os.getenv(
    'TIMESHEETS_ROOT',
    os.path.join(ONEDRIVE_ROOT, r'Ben Price\'s files - WESTONS SAFETY STAFFING\Automation\01. Timesheets')
)

# Configuration flags
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'

# Google Sheets
MAIN_SHEET_ID = os.getenv('MAIN_SHEET_ID', '1v-UmAkTbuHsJa1V_6-bDJuLc1jv8ZnfiS2SxP-Q2Oec')
```

**Update .gitignore:**

```gitignore
# Environment configuration
.env
.env.local
*.env
```

**Create a project-level `.env.template` (commit this!):**

```env
# .env.template - Template for environment configuration
# Place this file in the project folder (next to your scripts) and copy to .env

# OneDrive paths (adjust for your machine)
ONEDRIVE_ROOT=C:\Users\YOUR_USERNAME\OneDrive\OneDrive - WESTONS CORPORATION
TIMESHEETS_ROOT=${ONEDRIVE_ROOT}\Ben Price's files - WESTONS SAFETY STAFFING\Automation\01. Timesheets

# Google Sheets IDs
MAIN_SHEET_ID=your_sheet_id_here

# Development settings
DEBUG_MODE=True
DRY_RUN=False
```

---

## 4. Backup Strategy

### Why It Matters (Backup Strategy)

Protect against:

- Accidental data deletion
- Script bugs corrupting data
- Need to rollback changes
- Audit trail

### Implementation (Backup Strategy)

**Google Sheets Backup:**

```python
from datetime import datetime
import gspread
from logger_config import setup_logger

logger = setup_logger('backup')

def backup_google_sheet(sheet_id: str, backup_folder_id: str) -> str:
    """
    Create backup copy of Google Sheet before modifications.

    Args:
        sheet_id: Source sheet ID
        backup_folder_id: Google Drive folder for backups

    Returns:
        Backup sheet ID
    """
    try:
        gc = gspread.service_account(filename='credentials.json')
        source_sheet = gc.open_by_key(sheet_id)

        # Generate backup name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"Backup_{source_sheet.title}_{timestamp}"

        # Copy to backup folder
        backup_sheet = gc.copy(
            file_id=sheet_id,
            title=backup_name,
            folder_id=backup_folder_id
        )

        logger.info(f"✅ Created backup: {backup_name} (ID: {backup_sheet.id})")
        return backup_sheet.id

    except Exception as e:
        logger.error(f"❌ Backup failed: {e}", exc_info=True)
        raise

def process_with_backup(sheet_id: str, backup_folder_id: str):
    """Process data with automatic backup"""

    # Create backup first
    backup_id = backup_google_sheet(sheet_id, backup_folder_id)
    logger.info(f"Backup created: {backup_id}")

    try:
        # Your processing logic here
        process_sheet_data(sheet_id)
        logger.info("✅ Processing completed successfully")

    except Exception as e:
        logger.error(f"❌ Processing failed. Backup available: {backup_id}")
        raise
```

**Local File Backup:**

```python
import shutil
from pathlib import Path

def backup_file(file_path: str, backup_dir: str = '.archive/backups') -> str:
    """
    Create timestamped backup of file.

    Args:
        file_path: File to backup
        backup_dir: Directory for backups

    Returns:
        Path to backup file
    """
    source = Path(file_path)

    if not source.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Create backup directory
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    # Generate backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_path / f"{source.stem}_{timestamp}{source.suffix}"

    # Copy file
    shutil.copy2(source, backup_file)
    logger.info(f"✅ Backup created: {backup_file}")

    return str(backup_file)
```

**Automatic Cleanup (keep last 30 days):**

```python
from datetime import datetime, timedelta
import os

def cleanup_old_backups(backup_dir: str, days_to_keep: int = 30):
    """Delete backups older than specified days"""
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)

    deleted_count = 0
    for file_path in Path(backup_dir).glob('*'):
        if file_path.is_file():
            file_time = datetime.fromtimestamp(file_path.stat().st_mtime)

            if file_time < cutoff_date:
                file_path.unlink()
                deleted_count += 1
                logger.info(f"Deleted old backup: {file_path.name}")

    logger.info(f"✅ Cleanup complete: Deleted {deleted_count} old backups")
```

---

## 5. Health Checks & Monitoring

### Why It Matters (Health Checks & Monitoring)

Proactive monitoring prevents:

- Silent failures
- Discovering issues too late
- Manual log checking

### Implementation (Health Checks & Monitoring)

**Email Notifications (using SMTP):**

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_failure_notification(
    script_name: str,
    error_message: str,
    log_file: str = None
):
    """
    Send email notification when automation fails.

    Args:
        script_name: Name of failed script
        error_message: Error description
        log_file: Path to log file (optional)
    """
    # Email configuration (use environment variables!)
    sender_email = os.getenv('ALERT_EMAIL_FROM')
    recipient_email = os.getenv('ALERT_EMAIL_TO')
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_password = os.getenv('SMTP_PASSWORD')

    if not all([sender_email, recipient_email, smtp_password]):
        logger.warning("Email credentials not configured, skipping notification")
        return

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"🚨 Automation Failure: {script_name}"

    # Email body
    body = f"""
    <html>
    <body>
        <h2>Automation Failure Alert</h2>
        <p><strong>Script:</strong> {script_name}</p>
        <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Error:</strong></p>
        <pre>{error_message}</pre>

        {f'<p><strong>Log File:</strong> {log_file}</p>' if log_file else ''}

        <p>Please check the logs and resolve the issue.</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    # Send email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, smtp_password)
            server.send_message(msg)

        logger.info(f"✅ Failure notification sent to {recipient_email}")

    except Exception as e:
        logger.error(f"❌ Failed to send email notification: {e}")

def send_success_summary(script_name: str, summary: dict):
    """Send success notification with processing summary"""
    # Similar implementation with success template
    pass
```

**Webhook Notifications (Slack, Discord, etc.):**

```python
import requests

def send_slack_notification(message: str, webhook_url: str = None):
    """
    Send notification to Slack channel.

    Args:
        message: Notification message
        webhook_url: Slack webhook URL (from environment)
    """
    webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')

    if not webhook_url:
        logger.warning("Slack webhook not configured")
        return

    payload = {
        'text': message,
        'username': 'Automation Bot',
        'icon_emoji': ':robot_face:'
    }

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        logger.info("✅ Slack notification sent")
    except Exception as e:
        logger.error(f"❌ Slack notification failed: {e}")

# Usage in scripts
def main():
    logger = setup_logger('payroll')
    log_automation_start(logger, "Payroll Processing", "Export payroll data")

    try:
        # Your automation code
        result = process_payroll()

        # Success notification
        send_slack_notification(
            f"✅ Payroll processing completed successfully\\n"
            f"Records: {result['count']}\\n"
            f"Total: ${result['total']:,.2f}"
        )

        log_automation_end(logger, "Payroll Processing", success=True)

    except Exception as e:
        # Failure notification
        log_file = f"logs/payroll_{datetime.now().strftime('%Y%m%d')}.log"

        send_failure_notification(
            "Payroll Processing",
            str(e),
            log_file
        )

        send_slack_notification(
            f"🚨 Payroll processing FAILED\\n"
            f"Error: {str(e)}"
        )

        log_automation_end(logger, "Payroll Processing", success=False)
        raise
```

---

## 6. Performance Monitoring

### Why It Matters (Performance Monitoring)

Track performance over time to:

- Detect slowdowns
- Identify bottlenecks
- Plan optimizations
- Capacity planning

### Implementation (Performance Monitoring)

**Simple Performance Tracking:**

```python
import time
from datetime import datetime
import csv
from pathlib import Path

def track_performance(operation_name: str):
    """Decorator to track function execution time"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                success = True
                error = None
            except Exception as e:
                result = None
                success = False
                error = str(e)
                raise
            finally:
                elapsed = time.time() - start_time

                # Log performance
                log_performance(operation_name, elapsed, success, error)

                if elapsed > 60:
                    logger.warning(f"⚠️ {operation_name} took {elapsed:.1f}s (>1 min)")

            return result

        return wrapper
    return decorator

def log_performance(operation: str, elapsed: float, success: bool, error: str = None):
    """Log performance data to CSV"""
    perf_log = Path('.archive/performance_log.csv')

    # Create file with headers if doesn't exist
    if not perf_log.exists():
        with open(perf_log, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'operation', 'elapsed_seconds', 'success', 'error'])

    # Append performance data
    with open(perf_log, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            operation,
            f'{elapsed:.2f}',
            success,
            error or ''
        ])

# Usage
@track_performance('payroll_processing')
def process_payroll():
    """Process payroll data"""
    # Your code here
    pass

@track_performance('google_sheets_load')
def load_timesheet_data(sheet_id):
    """Load data from Google Sheets"""
    # Your code here
    pass
```

**Performance Analysis Script:**

```python
import pandas as pd
import matplotlib.pyplot as plt

def analyze_performance(log_file: str = '.archive/performance_log.csv'):
    """Analyze performance trends"""
    df = pd.read_csv(log_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Calculate statistics
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]

        print(f"\n{operation}:")
        print(f"  Average: {op_data['elapsed_seconds'].mean():.2f}s")
        print(f"  Median: {op_data['elapsed_seconds'].median():.2f}s")
        print(f"  Max: {op_data['elapsed_seconds'].max():.2f}s")
        print(f"  Success Rate: {op_data['success'].mean() * 100:.1f}%")

    # Plot trends
    for operation in df['operation'].unique():
        op_data = df[df['operation'] == operation]

        plt.figure(figsize=(10, 6))
        plt.plot(op_data['timestamp'], op_data['elapsed_seconds'])
        plt.title(f'Performance Trend: {operation}')
        plt.xlabel('Time')
        plt.ylabel('Duration (seconds)')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(f'.archive/perf_{operation}.png')
        plt.close()

    print("\n✅ Performance analysis complete. Charts saved to .archive/")
```

---

## 7. Code Documentation Standards

### Why It Matters (Code Documentation Standards)

Good documentation:

- Helps future you understand past decisions
- Enables collaboration
- Reduces onboarding time
- Serves as reference

### Implementation (Code Documentation Standards)

**Function Docstring Template:**

```python
def calculate_payroll_total(
    hours: float,
    rate: float,
    overtime_multiplier: float = 1.5
) -> dict:
    """
    Calculate total payroll including overtime.

    Calculates regular pay (up to 40 hours) and overtime pay (hours over 40)
    at the specified multiplier rate. This follows standard US overtime rules.

    Args:
        hours (float): Total hours worked in the pay period
        rate (float): Hourly rate in dollars
        overtime_multiplier (float, optional): Overtime rate multiplier.
            Defaults to 1.5 (time-and-a-half).

    Returns:
        dict: Payroll breakdown containing:
            - regular_hours (float): Hours at regular rate (max 40)
            - overtime_hours (float): Hours at overtime rate
            - regular_pay (float): Payment for regular hours
            - overtime_pay (float): Payment for overtime hours
            - total_pay (float): Total compensation

    Raises:
        ValueError: If hours or rate is negative
        ValueError: If overtime_multiplier is less than 1.0

    Examples:
        >>> calculate_payroll_total(45, 20.0)
        {
            'regular_hours': 40,
            'overtime_hours': 5,
            'regular_pay': 800.0,
            'overtime_pay': 150.0,
            'total_pay': 950.0
        }

        >>> calculate_payroll_total(35, 25.0)
        {
            'regular_hours': 35,
            'overtime_hours': 0,
            'regular_pay': 875.0,
            'overtime_pay': 0.0,
            'total_pay': 875.0
        }

    Notes:
        - This function does NOT handle double-time or other special rates
        - Does NOT account for taxes or deductions
        - Assumes standard 40-hour work week
    """
    # Validation
    if hours < 0 or rate < 0:
        raise ValueError("Hours and rate must be non-negative")

    if overtime_multiplier < 1.0:
        raise ValueError("Overtime multiplier must be >= 1.0")

    # Calculate regular and overtime
    regular_hours = min(hours, 40)
    overtime_hours = max(hours - 40, 0)

    regular_pay = regular_hours * rate
    overtime_pay = overtime_hours * rate * overtime_multiplier
    total_pay = regular_pay + overtime_pay

    return {
        'regular_hours': regular_hours,
        'overtime_hours': overtime_hours,
        'regular_pay': regular_pay,
        'overtime_pay': overtime_pay,
        'total_pay': total_pay
    }
```

**Class Docstring Template:**

```python
class PayrollProcessor:
    """
    Process payroll data from timesheets to ADP export.

    This class handles the complete payroll workflow:
    1. Load timesheet data from Google Sheets
    2. Calculate pay including overtime and per diem
    3. Validate employee information
    4. Export to ADP-compatible CSV format

    Attributes:
        sheet_id (str): Google Sheets ID for timesheet data
        pay_period_start (date): Start date of pay period
        pay_period_end (date): End date of pay period
        employees (dict): Employee information (loaded on init)

    Example:
        ```python

        processor = PayrollProcessor(
            sheet_id='abc123',
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 15)
        )

        results = processor.process()
        processor.export_to_csv('payroll_export.csv')

        ```text
    """

    def __init__(self, sheet_id: str, start_date: date, end_date: date):
        """
        Initialize payroll processor.

        Args:
            sheet_id: Google Sheets ID containing timesheet data
            start_date: Pay period start date (inclusive)
            end_date: Pay period end date (inclusive)

        Raises:
            ValueError: If end_date is before start_date
            ConnectionError: If cannot connect to Google Sheets
        """
        pass
```

**Module/File Docstring:**

```python
"""
Payroll Processing Module

This module handles automated payroll processing for Westons Safety Staffing,
including timesheet data extraction, pay calculations, and ADP export generation.

Main Components:
    - PayrollProcessor: Main processing class
    - calculate_payroll_total(): Overtime calculation
    - validate_timesheet_data(): Input validation
    - export_to_adp(): ADP CSV export

Dependencies:
    - Google Sheets API (gspread)
    - pandas for data manipulation
    - logger_config for logging

Configuration:
    - Requires wss_credentials.json for Google Sheets access
    - Paths configured in paths.py
    - See README.md for setup instructions

Author: Jay Ryan
Last Updated: 2025-10-12
"""
```

---

## 8. Dependency Management

### Why It Matters (Dependency Management)

Unpinned dependencies cause:

- Breaking changes on updates
- Inconsistent behavior across environments
- Difficult debugging
- "Works on my machine" problems

### Implementation (Dependency Management)

**Pinned Requirements (requirements.txt):**

```txt
# Core automation
gspread==6.0.0
oauth2client==4.1.3
google-auth==2.25.0
pandas==2.1.4

# Web automation
selenium==4.35.0
beautifulsoup4==4.13.4

# API clients
requests==2.32.4
flask==3.0.0

# Testing
pytest==8.4.2
pytest-cov==7.0.0

# Error handling
tenacity==9.0.0

# Environment management
python-dotenv==1.1.1
```

**Update Strategy:**

```bash
# Check for outdated packages
pip list --outdated

# Update specific package (test first!)
pip install --upgrade gspread

# Regenerate requirements
pip freeze > requirements.txt

# Test thoroughly before committing
pytest tests/ -v
```

**Development vs Production:**

```txt
# requirements.txt - Production dependencies
gspread==6.0.0
pandas==2.1.4
flask==3.0.0

# requirements-dev.txt - Development tools
-r requirements.txt  # Include production deps
pytest==8.4.2
pytest-cov==7.0.0
black==25.1.0  # Code formatter
flake8==8.0.0  # Linter
ipython==8.12.3  # Interactive shell
```

---

## 📚 Quick Reference

### Implementation Priority

**Critical (Do First):**

1. ✅ Input validation - Prevent bad data
1. ✅ Retry logic - Handle temporary failures
1. ✅ Error notifications - Know when things break

**Important (Do Soon):**

1. ✅ Backup strategy - Protect data
1. ✅ Environment variables - Portability
1. ✅ Documentation - Future-proof

**Nice to Have (When Time Permits):**

1. ✅ Performance monitoring - Optimization
1. ✅ Dependency pinning - Stability

---

## 🎯 Implementation Checklist

Before deploying any new automation:

- [ ] Input validation on all external data
- [ ] Retry logic on all API calls
- [ ] Error notifications configured
- [ ] Backup created before modifications
- [ ] Logging implemented
- [ ] Tests written for calculations
- [ ] Documentation added
- [ ] Dry-run mode tested
- [ ] Dependencies pinned

---

For questions or clarifications, refer to the AI agent via copilot-instructions.md.
