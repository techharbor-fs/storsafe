# Edge → Yardi (GL Journal Import) — PROJECT

## Overview

This project will automate taking Edge month-end exports and recording them in Yardi via **GL Journal Import**.

Key constraint (confirmed): the **CSV export is missing reliable property attribution**, so the workflow is **PDF-first**.

Important: any month “detail CSV” should **not** be treated as the source of truth for property codes. Use the provided **Property Codes.xlsx** (or equivalent reference) for property-code lookups.

End-state goal: a monthly workflow that:

1) ingests the Edge PDF(s)
2) extracts transactions/summary lines per property
3) maps Edge property/account identifiers to Yardi identifiers
4) generates a Yardi GL Journal Import file (CSV)
5) uploads/posts to Yardi (API if available; otherwise UI-assisted import)
6) verifies control totals

## Current Inputs (as of Dec)

Example month folder:

- `12. Dec/production_combined_general_ledger.pdf`

After Phase 1 rename (canonical Input name):

- `12. Dec/Input/edge_gl_2025-12.pdf`

Observed from initial inspection:

- The PDF includes per-property sections with header lines like:
  - `StorSafe of Altoona - ...`
  - `StorSafe of Cary - ...`
  - `StorSafe of Crystal Lake - ...`
  - `StorSafe of Northfield - ...`
- Each section contains a repeated table with columns:
  - `Category | Subcategory | Description | Code | Debit | Credit`

## Workflow by Phases

### Phase 0 — Define the posting contract (one-time)

Lock down how Edge data should become a Yardi GL journal import.

Deliverables:

- Required Yardi import format (columns, batch naming convention, required balancing rules)
- Property identity mapping (Edge property label → Yardi entity/property code)
- Account mapping: not required if the PDF "Code" is already the Yardi account code (current assumption)
- A “golden month” sample folder used as the regression baseline

### Phase 1 — Monthly intake + inspection (no Yardi writes)

Goal: reliably understand what the month folder contains.

Steps:

1) Detect expected input files (PDF and/or any CSVs)
2) Inspect PDF structure:
   - page count
   - which pages belong to which property
   - presence of expected column headers
3) Output evidence artifacts:
   - `Output/inspection_summary.json`
   - `Output/inspection_preview.txt`

Success criteria:

- We can deterministically split the PDF into property sections and report the page ranges.

### Phase 2 — Normalize Edge PDF into canonical tabular data

Goal: create a single canonical dataset we control.

Canonical columns (draft):

- `period_month` (e.g., `2025-12`)
- `property_name` (e.g., `StorSafe of Cary`)
- `category`, `subcategory`, `description`
- `edge_code` (may be blank)
- `debit`, `credit`
- `source_file`, `source_page`

Outputs:

- `Output/edge_normalized.csv`
- `Output/normalization_summary.json`

Success criteria:

- Row counts are stable run-to-run.
- Debits and credits parse cleanly as numbers.

### Phase 3 — Mapping (Edge → Yardi)

Goal: map properties to Yardi identifiers.

Recommended mapping sources:

- A Google Sheet (similar to existing StorEdge/Yardi mapping patterns), OR
- Versioned CSV mapping files under this folder

Outputs:

- `Output/mapping_report.xlsx` (unmapped items highlighted)

Success criteria:

- No unmapped properties (or an explicit allowlist for exceptions).

### Phase 4 — Generate Yardi GL Journal Import file

Goal: produce the exact CSV Yardi expects.

Outputs:

- `Output/yardi_gl_journal_import_<batch>.csv`
- `Output/control_totals.json` (Edge totals vs import totals)

Success criteria:

- Import file balances (sum debits == sum credits) per required batch rules.

### Phase 5 — Upload/post to Yardi

Two implementations (phase-gated):

- **5A Manual upload (initial / safest)**
  - Workflow generates the import CSV and prints a short checklist for importing in Yardi.

- **5B Automated upload (later)**
  - **API-first** if Yardi exposes an accessible integration endpoint for journal imports.
  - Otherwise, a **UI-assisted** import using Playwright (pattern exists in other automation).

Notes on “API if possible”:

- Yardi integrations vary widely by product/tenant (Voyager web services/SOAP, etc.).
- This project will be structured so Phase 4 (file generation) is stable regardless of whether Phase 5 uses API or UI.

### Phase 6 — Verification

Goal: confirm what was posted matches the source.

Outputs:

- `Output/posting_verification.json`

Success criteria:

- Control totals match.
- A Yardi batch identifier / confirmation evidence is saved.

## “Initial Workflow” (what we build first)

First production milestone is Phases 1–4 (no Yardi writes):

1) month folder selection
2) inspect/split PDF by property
3) normalize into canonical CSV
4) generate a draft Yardi import CSV + control totals

After accountants confirm the import file is correct, we add Phase 5 (upload) and Phase 6 (verification).

## Proposed Folder Layout (target)

```text
09. Edge to Yardi/
├── PROJECT.md
├── RUN_ME.py                       # (to be added) single entrypoint for monthly run
├── internal/                       # (to be added) real workflow code
├── 12. Dec/
│   ├── Input/
│   └── Output/
│       ├── inspection_summary.json
│       ├── edge_normalized.csv
│       └── yardi_gl_journal_import_<batch>.csv
```

## Next Step

If you give the go-ahead, I’ll scaffold the Phase 1 runner (entrypoint + `internal/` scripts) and implement the PDF inspection + property page-range detection using PyMuPDF.

## Last Updated

- 2026-01-07
