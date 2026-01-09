# Cash Flow Report 2 (Google Sheets) — PROJECT

## Overview

This folder automates the monthly "Property Cash Flow" Google Sheet build.

High-level workflow:

1) Copy authoritative template tabs + month-end list + HA‑CF formatting tabs into the target workbook.
2) Upload the month’s Yardi Excel exports into the HA‑CF tabs (values only; formatting preserved).
3) Upload the Balance Sheet export into `HA-BS-<MON>` tab.
4) Generate formulas into `PORTFOLIO CASH FLOW` and apply row highlighting based on Month End List status.

Unified workflow also builds the legacy v1-style statement tabs in the same target workbook:

- Run the v1 generator twice (monthly + ytd), producing:
  - `Cash Flow Report (All) - <Mon>`
  - `Cash Flow Report (All) - YTD.<Mon>`
- v1 reads source data from the same `HA-CF-*` / `HA-BS-*` tabs uploaded by v2.

During preparation, the month folder exports are also renamed to deterministic filenames (per-month folder) so future runs can reliably re-detect them.

## Main entrypoint (run everything)

Use this as the single "activation script" moving forward:

- `RUN_ME.py`

Example:

```bash
python RUN_ME.py \
  --month-folder "11. Nov" \
  --target-sheet "https://docs.google.com/spreadsheets/d/<id>/edit" \
  --confirm \
  --assume-yes
```

To skip generating the v1 statement tabs:

```bash
python RUN_ME.py \
  --month-folder "11. Nov" \
  --target-sheet "https://docs.google.com/spreadsheets/d/<id>/edit" \
  --confirm \
  --assume-yes \
  --skip-v1
```

### Cleanup behavior (default)

The workflow deletes every other tab in the workbook and keeps only the required Cash Flow tabs.

This is destructive, but it is still guarded by `--confirm` (dry-run prints what would be deleted).

```bash
python RUN_ME.py \
  --month-folder "11. Nov" \
  --target-sheet "https://docs.google.com/spreadsheets/d/<id>/edit" \
  --confirm \
  --assume-yes
```

Cleanup is part of the process and is not optional.

## Component scripts

 

### 1) Prepare / rebuild workbook

- `prepare_monthly_cashflow_workbook.py`
  - Copies tabs into the target workbook:
    - `PORTFOLIO CASH FLOW`
    - `PROPERTY CODES`
    - `Property Status`
    - `Bank Rec priorities` → `MONTH END LIST`
    - `HA-CF-OCT` → `HA-CF-<MON>` (month tab)
    - `HA-CF-3MOS`
    - `HA-CF-YTD`
  - Uploads month-folder exports into the HA‑CF tabs (values only).

### 2) Generate formulas + highlighting

- `generate_property_cashflow_report.py`
  - Writes formulas into `PORTFOLIO CASH FLOW` for:
    - Last Month
    - Last 3 Months
    - YTD
  - Applies yellow highlights to portfolio rows where Balance Sheet recon is not done in `MONTH END LIST`.

## Configuration

Required Google service account env var:

- `SERVICE_ACCOUNT_JSON` (preferred) OR
- `GOOGLE_APPLICATION_CREDENTIALS` / `SERVICE_ACCOUNT_FILE`

The target spreadsheet must be shared with the service account email.

## Notes / conventions

- Yellow highlight intentionally skips the gray separator columns in `PORTFOLIO CASH FLOW`.
- Balance Sheet recon highlighting:
  - If the Balance Sheet recon cell value is `n/a`, the property is NOT highlighted.
  - Otherwise, a green Balance Sheet recon cell means done; non-green means highlight.

## Last updated

2026-01-02
