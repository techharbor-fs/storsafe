# Bank Reconciliation Web App

**Last Updated:** January 21, 2026

## Overview

A web application for automating bank reconciliation between bank statements (PDF) and Yardi data (Excel). Replaces the previous Google Sheets-based workflow with a local SQLite database and Flask web interface.

## Key Files & Roles

| File | Purpose |
|------|---------|
| `run_bank_rec_app.py` | Entry point - starts Flask development server |
| `internal/app.py` | Flask app factory |
| `internal/config.py` | Configuration (paths, settings) |
| `internal/database/schema.sql` | SQLite database schema |
| `internal/database/db.py` | Database connection and initialization |
| `internal/matching/engine.py` | 7-pass auto-matching algorithm |
| `internal/parsers/` | PDF and Excel parsing |
| `internal/parsers/yardi_excel.py` | Yardi Excel parser with analysis and rename functions |
| `internal/routes/` | Flask route handlers (dashboard, upload) |
| `internal/templates/` | Jinja2 HTML templates |
| `internal/rename_yardi_reports.py` | CLI utility - analyzes and renames Yardi Excel files |
| `internal/check_db.py` | Database inspection helper |
| `tests/` | Test suite folder |
| `.archive/` | Archived legacy code (old Google Sheets version) |

## How It Works

```
1. Select Folder → User selects monthly folder (e.g., "12. Dec/")
                       ↓
2. Validate → System checks folder name for expected month
            → Scans for PDF + Excel files
            → Validates file contents match expected period
                       ↓
3. Parse → Extract transactions from both sources
         → Auto-detect property name from files
                       ↓
4. Store → Save to SQLite database
                       ↓
5. Auto-Match → Run 7-pass matching algorithm
                       ↓
6. Review → View matched/unmatched in web UI
                       ↓
7. Manual Match → Select unmatched items to match manually
```

### Folder-Based Validation

The app uses folder name to determine the **expected period**:

| Folder Name | Expected Period |
|-------------|-----------------|
| `12. Dec` | December (current year) |
| `11. Nov` | November (current year) |
| `December 2025` | December 2025 |

**Sanity Checks:**
- Bank PDF transaction dates must be in the expected month
- Yardi Excel report period must match the expected month
- Both PDF and Excel files must exist in the folder

If validation fails, the app shows an error and prevents processing.

## Database Schema

- **properties** - Property names (Madison, Chicago, etc.)
- **reconciliation_periods** - Property + Year/Month combinations
- **bank_transactions** - Transactions from bank PDF
- **yardi_transactions** - Transactions from Yardi Excel
- **matches** - Matched transaction groups (1:1 or many:many)
- **match_bank_transactions** - Many-to-many link table
- **match_yardi_transactions** - Many-to-many link table

## How to Run

```bash
# From the project folder
cd "08. Bank Reconciliation"

# Install Flask if not already installed
pip install Flask

# Run the app
python run_bank_rec_app.py

# Open in browser
# http://localhost:5000
```

## Yardi Report Renaming

The parser analyzes Yardi Bank_Rec Excel files and can automatically rename them to a standardized format:

**Format:** `{Year}-{Month}_Bank_Rec_{Property}.xlsx`  
**Example:** `Bank_Rec.xlsx` → `2025-12_Bank_Rec_Madison.xlsx`

### Using the CLI Tool

```bash
# Dry run - see what would be renamed (no changes)
python internal/rename_yardi_reports.py "12. Dec"

# Actually rename files
python internal/rename_yardi_reports.py "12. Dec" --rename

# Process all monthly folders
python internal/rename_yardi_reports.py . --rename
```

### How Detection Works

The parser extracts metadata by searching for:
1. **Property name**: Header text like "SS of Madison Notre Dame...", or filename pattern
2. **Period (Month/Year)**: 
   - Header dates ("as of 12/31/2025", "Period Ending December 31, 2025")
   - Date cells in the first 10 rows
   - Parent folder name ("12. Dec")
   - Existing filename format

Detection confidence levels:
- **high**: Property, month, and year all detected
- **medium**: Property detected but period uncertain
- **low**: Could not determine property name

## Development Phases

- **Phase 1** ✅ - Foundation: Flask structure, SQLite schema, basic routes
- **Phase 2** ✅ - Data Pipeline: Auto-matching after upload
- **Phase 3** ✅ - View Pages: Matched/unmatched transaction views, unmatch action
- **Phase 4** ✅ - Interactive Matching: Selection with live totals, manual matching
- **Phase 5** ✅ - Polish: Filters, export, completion workflow

## Testing

```bash
# Run all tests (unit + integration with real data)
python tests/test_matching.py

# Run with verbose output
python tests/test_matching.py -v

# Run only unit tests
python tests/test_matching.py --test unit

# Run only integration tests (with Nov/Dec real data)
python tests/test_matching.py --test integration

# End-to-end upload test (requires server running)
python run_bank_rec_app.py      # In one terminal
python tests/test_upload_e2e.py  # In another terminal

# Quick database check
python internal/check_db.py
```

## Matching Algorithm (7 Passes)

Inherited from the original `bank_reconciliation.py`:

| Pass | Criteria | Notes |
|------|----------|-------|
| PASS 1 | Property + Transaction ID + Amount | Strict 1:1 |
| PASS 2 | Property + Date + Amount | Strict 1:1 |
| PASS 3 | Property + Amount + Date ±3 days | Strict 1:1 |
| PASS 4 | Property + Amount + Date ±7 days | Strict 1:1 |
| PASS 5 | Same-side reversals | Bank↔Bank or Yardi↔Yardi |
| PASS 6 | Property + Amount (equal counts) | All-or-nothing matching |
| PASS 7 | Property + Amount (unequal counts) | Suggested matches only |

## Known Quirks/Gotchas

- **Notre Dame FCU PDF format**: Uses multi-line transaction blocks, soft hyphens for negative amounts
- **Yardi Excel format**: Outstanding Checks in columns C/F/H/I, Other Items in C/H/I
- **Property name extraction**: Searched in PDF header and Excel header/filename

## Configuration

- **Database**: `data/bank_rec.db` (SQLite)
- **Uploads**: `data/uploads/` (temporary, cleaned after processing)
- **Port**: 5000 (Flask development server)

## Tech Stack

- **Backend**: Flask + SQLite
- **Frontend**: Tailwind CSS + HTMX + Alpine.js
- **Parsing**: PyMuPDF (PDF), openpyxl (Excel)
