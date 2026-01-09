# Report Compiler

**Project Location**: `automation files/03. storsafe/0. Report Compiler/`
**Created**: December 22, 2025
**Purpose**: Compile 3 source Excel files per property into a single Financial Report workbook.

---

## Overview

This script takes individual report exports (12 Month Statement, Cash Flow, General Ledger) from the accounting system and combines them into a single workbook per property. The output format matches the manual compilation previously done by accountants.

---

## Key Files & Roles

| File | Purpose |
|------|---------|
| `compile_reports.py` | Main script that combines source files |
| `Input/` | Source files to compile |
| `Output/` | Compiled Financial Report workbooks |

---

## How It Works

1. Scans `Input/` folder for files matching patterns:
   - `12_Month_Statement_<code>_Accrual.xlsx`
   - `Cash_Flow_<code>_Accrual.xlsx`
   - `GeneralLedger_<code>_Accrual.xlsx`

1. Groups files by property code (e.g., `smsaltoo`, `smscary`)

1. For each complete property set:
   - Creates new workbook with 3 sheets in order:
     1. `General Ledger`
     1. `Cash Flow`
     1. `12 Month Statement`
   - Copies all cell values, formatting, column widths, row heights

1. Saves output as `SMS-<PropertyName> <MM.DD.YY> Financial Report_Final.xlsx`

---

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--input-folder` | `./Input` | Folder containing source files |
| `--output-folder` | `./Output` | Folder for compiled reports |
| `--report-month` | *(required)* | Reporting month in YYYY-MM format |

---

## Property Mappings

| Code | Display Name |
|------|--------------|
| `smsaltoo` | Altoona |
| `smscary` | Cary |
| `smscrys` | Crystal Lake |
| `smsnfss` | NFSS |

---

## How to Run

```powershell
& "C:\Users\jayry\python projects\automation files\03. storsafe\.venv\Scripts\python.exe" `
  "compile_reports.py" `
  --report-month 2025-11
```

---

## Expected Behavior

- Compiles all 4 properties if all source files present
- Skips properties with missing source files (logs warning)
- Output files saved to `Output/` folder
- Sheet order always: General Ledger → Cash Flow → 12 Month Statement

---

## Last Updated

- **Date**: December 22, 2025
- **Maintainer**: StorSafe Automation Team
