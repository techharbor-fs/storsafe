# SMS Distribution Recommendation Pack

**Project Location**: `automation files/03. storsafe/5. SMS Reports/`  \
**Created**: November 21, 2025  \
**Purpose**: Generate and verify the SMS monthly "Distribution Recommendation" workbooks by linking the manual template to each property's Cash Flow workbook.

---

## Overview

This project reverse-engineers the hand-built SMS distribution sheets (Altoona, Cary, Crystal Lake, NFSS) and recreates them with openpyxl so every property pulls live balances from its financial workbook. Helper utilities compare generated files against the archived manual versions and trace cells back to their Cash Flow origins, allowing us to codify property-specific logic differences (notably NFSS).

---

## Core Features

1. **Formula Builder (`.helper_artifacts/generate_distribution_report.py`)**
   - CLI tool that fabricates a fresh distribution sheet for any property/month.
   - Reads the property-specific Cash Flow workbook, locates the "Ending Balance", "NET INCOME", and "Note 1 Principal" rows, and wires Sheet1 values to those cells via external references.
   - Supports overrides for operating hold, manual B15 value, and the "Current Balance" display date.

1. **Workbook Comparator (`.helper_artifacts/compare_distribution_reports.py`)**
   - Diffs any manual workbook vs. the generated candidate, highlighting cell values, formulas, number formats, fonts/fills, column widths, and row heights.
   - Used as the regression gate when validating Cary, Crystal Lake, and NFSS against their September 2025 baselines.

1. **Provenance Mapper (`.helper_artifacts/map_distribution_to_financial.py`)**
   - Consumes the JSON output from `extract_workbook_structure.py` to propose the Cash Flow cells that feed each distribution cell.
   - Scores candidates by formula references, numeric similarity, and label proximity to document why a given external link exists.
1. **Monthly Batch Driver (`generate_monthly_distribution_reports.py`)**
   - Production script that scans any `.Reports/<MM. Month>/` folder for `SMS-*.xlsx` financial workbooks, derives the property name/output label, and calls the helper generator for each property.
   - Outputs fully formatted distribution workbooks (e.g., `10.2025 SMS - Cary Distribution recommendation.xlsx`) beside their financial sources.
1. **Cash Balance Applier (`.helper_artifacts/apply_cash_balances.py`)**
   - Writes the latest “cash in bank today” amounts into `B15` for every generated workbook.
   - Accepts one or more `--balance Property=Amount` flags so each property can receive a different balance in one run.
   - Intended to run immediately after the batch driver so accountants no longer have to key B15 manually.
1. **Email Sender (`send_distribution_emails.py`)**
   - Finds each property's financial + distribution workbook inside the month folder and builds the email message.
   - Hardcodes the property-specific To/CC lists from the legacy messages so the right contacts always receive their files.
   - Defaults to a safe dry-run that prints the composed email; `--send` flips it into live mode using Outlook/Office 365 SMTP (`email_credentials.json` for user/pass).

---

## Technical Architecture

- **Inputs**: One financial workbook per property (e.g., `SMS-Altoona 09.30.25 Financial Report_Final.xlsx`) and the reporting month (YYYY-MM).
- **Cell Discovery**: `find_label_cell()` scans the Cash Flow sheet for the text labels "Ending Balance", "NET INCOME", and "Note 1 Principal" to capture their adjacent numeric cells.
- **External Reference Builder**: The helper constructs `='[Financial.xlsx]Cash Flow'!C113` style formulas so the distribution report stays synced with the authoritative workbook.
- **External Reference Builder**: The helper now emits fully-qualified links like `='C:/.../.Reports/09. Sep/[SMS-Cary ...xlsx]Cash Flow'!C113` so Excel can resolve balances even when the generated workbook lives in `.helper_artifacts/` or another folder.
- **Sheet Layout**: Column widths (A 27.71, B 34.14, **D 9.14**, E 9.29) and row heights (Row 6 = 6.75, Row 9 = 7.5) mirror the manual template; column D currently exists solely to align with the legacy sheet.
- **Styling**: Standard Aptos Narrow fonts, yellow fill on A8, custom currency formats (`_($* #,##0.00_)` for linked amounts and `"$"#,##0.00` for manual-entry cells like B15/B16).
- **Date Logic**: `B3` always renders `"as of mm.dd.yyyy"` based on the reporting month end. `A15`/`A16` default to the current CST date unless `--current-balance-date` overrides the label (used to align September 2025 comparisons).
- **Helper Ecosystem**: `extract_workbook_structure.py` captures cell metadata for provenance analysis, while `inspect_cell.py` inspects individual cell content when troubleshooting diffs.

---

## Expected Behavior

- `A3` references the Cash Flow "Ending Balance" row immediately below the "Ending Balance" label, respecting each property's workbook row numbers.
- `A7` stores a literal formula `=<net income>-<note principal>` (note principal already converted to a positive literal), keeping both captured values visible without using helper functions.
- `A8` uses `_xlfn.IFS(A7<0,0,A5<A7,0,A5>A7,A7)` to cap recommended distributions at zero when negative.
- `A8`/`A9` now rely on `MAX(0,MIN(A7,A5))` (wrapped in `IF(A8>0,...)` for NFSS) so Excel no longer injects `_xlfn` compatibility prefixes.
- `A4` stays at the `--operating-hold` default (`-10000` unless overridden).
- `B15` is left blank by default because accountants key the true bank balance manually.
- Manual comparison runs should only report differences for:
  - dynamic formulas vs. manually keyed values (A3, A7, A8),
  - optional column D width (baseline includes it; generator now matches),
  - property label variants (see NFSS below), and
  - B15 manual entry presence/absence.

---

## Configuration

| Option | Default | Description |
| --- | --- | --- |
| `--financial` | *(required)* | Path to the property Cash Flow workbook. |
| `--property-name` | *(required)* | Display name for `A1` (e.g., "Altoona"). |
| `--report-month` | *(required)* | `YYYY-MM` period used for `B3`, `B7`, and `A16` date stamps. |
| `--output` | *(required)* | Target XLSX path (store under `.helper_artifacts/` while validating). |
| `--operating-hold` | `-10000.0` | Injects A4 value before summing into A5. |
| `--b15-value` | `None` | Pre-populates B15 if we already know the balance. |
| `--current-balance-date` | `None` | Forces `A15`/`A16` to a specific date (use when matching historical screenshots). |

The helpers rely on Python 3.11+, `openpyxl`, and the shared venv at `C:/Users/jayry/python projects/.venv/`.

---

## Known Behaviors & Property Nuances

- **Altoona, Cary, Crystal Lake**:
  - Share identical labeling and layout: `B5 = "Cash available for distribution"`, B7 uses the reporting-month string, and only column E has a defined width besides A/B (column D exists for spacing parity).
  - Manual files typically include column D (9.14 width) even though it stays empty; generator sets it so diffs stay clean.
  - Cary’s historical sheet used hard-coded September dates while the template used TODAY()-based math; prefer the override flag during backfills to avoid label drift.

- **NFSS (Northfield)**:
  - Generator now switches to NFSS mode automatically (property name contains "Northfield"/"NFSS") and injects a dedicated `A8/B8` row labeled "Crown Castle payment". Row 8 is auto-populated by scanning the General Ledger tab for the Crown Castle entry (capturing the first positive debit) so the workbook reflects the exact payment without manual typing, and Row 9 carries the highlighted `_xlfn.IFS(...)+A8` formula.
  - Uses the same `B5 = "Cash available for distribution"` label to align with the new naming directive.
  - B15/B16 remain blank placeholders so Northfield can hand-enter balances right before finalizing distributions.
  - Expect comparison diffs around TODAY()-based labels and any manual entries (A8, B16) present in the legacy XLSX.

- **Manual Cells**:
  - `B15`, `B16`, A23/A24, and lower memo rows stay blank placeholders so accountants can free-type without fighting formulas.
  - Helper `apply_cash_balances.py` backfills B15 with known values, but cells remain editable in case someone needs to override them later.
  - Column B descriptive strings are always text, never formulas, even when they depend on the period (we inject `TEXT(DATE(...),"mmmm")`).

---

## Usage Patterns

1. **Generate a candidate workbook**:

   ```powershell
   & "C:/Users/jayry/python projects/.venv/Scripts/python.exe" \
     ".helper_artifacts/generate_distribution_report.py" \
     --financial ".Reports/09. Sep/SMS-Cary 09.30.25 Financial Report_Final.xlsx" \
     --property-name "Cary" \
     --report-month 2025-09 \
     --current-balance-date 2025-09-30 \
     --output ".helper_artifacts/Cary_2025-09_distribution_generated.xlsx"
   ```

1. **Compare to the manual baseline**:

   ```powershell
   & "C:/Users/jayry/python projects/.venv/Scripts/python.exe" \
     ".helper_artifacts/compare_distribution_reports.py" \
     ".Reports/09. Sep/09.2025 SMS - Cary Distribution recommendation.xlsx" \
     ".helper_artifacts/Cary_2025-09_distribution_generated.xlsx"
   ```

1. **Investigate anomalies**:
   - Use `inspect_cell.py` to read or edit specific cells.
   - Run `extract_workbook_structure.py` + `map_distribution_to_financial.py` when we need a provenance report for auditors.

1. **Document deltas**:
   - Capture expected manual-only differences (B15 values, narrative labels) inside this `PROJECT.md` before changing generator defaults.

1. **Run the monthly batch (production)**:

   ```powershell
   & "C:/Users/jayry/python projects/.venv/Scripts/python.exe" \
     "generate_monthly_distribution_reports.py" \
     --reports-folder ".Reports/10. Oct" \
     --report-month 2025-10 \
     --current-balance-date 2025-10-31
   ```

   - The script loops through every `SMS-<Property> *.xlsx` financial workbook inside the target folder and writes the finished distribution files (e.g., `10.2025 SMS - Cary Distribution recommendation.xlsx`) into that same folder.

1. **Apply cash balances**:

    ```powershell
    & "C:/Users/jayry/python projects/.venv/Scripts/python.exe" \
       ".helper_artifacts/apply_cash_balances.py" \
       --reports-folder ".Reports/10. Oct" \
       --balance "Altoona=20915.03" \
       --balance "Cary=51028.11" \
       --balance "Crystal Lake=24682.95" \
       --balance "NFSS=9245.65"
    ```

   - Reuses the property names from `Sheet1!A1`, so we can hit multiple workbooks in one pass.
   - Skips properties whose balances were not supplied, preserving manual-entry flexibility.

1. **Send the emails**:

   ```powershell
   & "C:/Users/jayry/python projects/.venv/Scripts/python.exe" \
     "send_distribution_emails.py" \
     --reports-folder ".Reports/10. Oct" \
     --report-month 2025-10          # add --send once you're ready to mail
   ```

   - Dry-run output shows Subject/To/Cc/attachments for each property.
   - When `--send` is present the script reads `email_credentials.json` (jvillasurda@storsafe.com) and sends via Outlook SMTP (`smtp.office365.com:587` + STARTTLS).

---

## File Structure Snapshot

```text
5. SMS Reports/
├── .Reports/09. Sep/                  # Archived manual distribution workbooks + Cash Flow sources
├── .Reports/10. Oct/                  # Current month inputs/outputs (updated via batch script)
├── .helper_artifacts/
│   ├── generate_distribution_report.py
│   ├── compare_distribution_reports.py
│   ├── extract_workbook_structure.py
│   ├── map_distribution_to_financial.py
│   ├── inspect_cell.py
│   └── *_distribution_generated.xlsx  # Validation outputs
├── generate_monthly_distribution_reports.py  # Production batch entry point
├── logs/                              # Runtime logs (if enabled)
└── PROJECT.md                         # (this document)
```

---

## Last Updated

- **Date**: November 21, 2025 04:35 PM CT
- **Maintainer**: StorSafe Automation Team
- **Next Steps**: Dry-run the email sender each month, then re-run with `--send` once reviewed; expand recipient mappings if new properties onboard. Keep `email_credentials.json` out of git.
