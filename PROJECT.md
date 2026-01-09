# Storsafe - Project Documentation

## Project Overview

Automation scripts for Storsafe financial reporting, specifically Account Reconciliation and Cash Flow Reports.

## Roadmap & Active Tasks

No active tasks at this time.

## Resolved Issues & History

Imported from Legacy TODO_SS.md.

### [✓] Fix GL Account Categorization and Dynamic Reading (Nov 3, 2025)

- **Goal**: Correctly categorize accounts 1410, 1770, 1800, 1900, 1910 as Investing and read dynamic row counts.
- **Files**: `generate_cashflow_report.py`
- **Resolution**: Updated `categorize_gl_code` and dynamic reading logic. Verified with `validate_account_lists.py`.
