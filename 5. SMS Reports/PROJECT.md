# SMS Distribution Recommendation Pack

**Project Location**: `Storsafe/5. SMS Reports/`  
**Last Updated**: January 21, 2026  
**Purpose**: Generate SMS monthly "Distribution Recommendation" workbooks by extracting data from each property's Financial Report.

---

## Overview

This project automates the monthly SMS distribution recommendation workflow:
1. **Compile** downloaded reports into standard Financial Report format
2. **Generate** distribution recommendation workbooks with formulas linked to Cash Flow data
3. **Apply** cash balances from bank statements
4. **Email** the reports to property stakeholders

---

## File Structure

```text
5. SMS Reports/
├── run_sms_monthly_workflow.py    # LAUNCHER - single entry point
├── PROJECT.md                     # This documentation
├── internal/                      # All implementation modules
│   ├── compile_downloaded_reports.py
│   ├── generate_distribution_report.py
│   ├── generate_monthly_distribution_reports.py
│   └── send_distribution_emails.py
└── .Reports/                      # Monthly data folders
    ├── 09. Sep/
    ├── 10. Oct/
    ├── 11. Nov/
    └── 12. Dec/
        ├── SMS-Altoona 12.31.25 Financial Report_Final.xlsx
        ├── SMS-Cary 12.31.25 Financial Report_Final.xlsx
        ├── SMS-Crystal Lake 12.31.25 Financial Report_Final.xlsx
        ├── SMS-NFSS 12.31.25 Financial Report_Final.xlsx
        ├── 12.2025 SMS - Altoona Distribution recommendation.xlsx
        ├── 12.2025 SMS - Cary Distribution recommendation.xlsx
        ├── 12.2025 SMS - CLK Distribution recommendation.xlsx
        ├── 12.2025 SMS - NFSS Distribution recommendation.xlsx
        └── bank_balances.txt
```

---

## Usage

### Run Specific Steps

```powershell
# Step 1: Compile downloaded reports
py -3 run_sms_monthly_workflow.py --step compile --month "12. Dec" --report-date "12.31.25"

# Step 2: Generate distribution recommendations
py -3 run_sms_monthly_workflow.py --step distribute --month "12. Dec"

# Step 3: Apply cash balances (requires bank_balances.txt)
py -3 run_sms_monthly_workflow.py --step balances --month "12. Dec"

# Step 4: Preview emails (dry run)
py -3 run_sms_monthly_workflow.py --step email --month "12. Dec"

# Step 4: Send emails for real
py -3 run_sms_monthly_workflow.py --step email --month "12. Dec" --send
```

### Run Full Workflow

```powershell
py -3 run_sms_monthly_workflow.py --month "12. Dec" --report-date "12.31.25"
```

---

## Data Extraction Logic

All data is extracted **dynamically** - no hardcoded row/column positions.

| Distribution Field | Source | Extraction Logic |
|-------------------|--------|------------------|
| **Book Balance (A3)** | Cash Flow sheet | Find row with BOTH "Period to Date" AND "Ending Balance" headers → Find "Total Cash" row below → Get value in Ending Balance column |
| **Net Income (A7)** | Cash Flow sheet | Find "NET INCOME" label → Get first numeric value in that row |
| **Note 1 Principal (A7)** | Cash Flow sheet | Find "Note 1 Principal" label → Get first numeric value (typically negative) |
| **Crown Castle (A8, NFSS only)** | General Ledger sheet | Find "Crown Castle" rows → Sum only DEBIT entries (debit > 0 and credit = 0) |
| **Current Balance (B15)** | `bank_balances.txt` | Property: Amount format |

---

## bank_balances.txt Format

Create this file in the month folder before running the "balances" step:

```text
# Bank Balances for December 2025
# Format: Property: Amount
# Lines starting with # are comments

Altoona: 35767.41
Cary: 60419.11
Crystal Lake: 36101.11
NFSS: 4320.38
```

---

## Property-Specific Behavior

### Standard Properties (Altoona, Cary, Crystal Lake)

- Layout: Rows 1-8, 15-16
- A8 = `=MAX(0,MIN(A7,A5))` (distribution recommendation)

### NFSS (Northfield)

- Includes additional Row 8 for Crown Castle payment
- A9 = `=IF(A8>0,MAX(0,MIN(A7,A5))+A8,MAX(0,MIN(A7,A5)))` (distribution with Crown Castle)
- Crown Castle value extracted from General Ledger (sum of debit entries only)

---

## Module Descriptions

| Module | Purpose |
|--------|---------|
| `run_sms_monthly_workflow.py` | Launcher script - orchestrates all steps |
| `internal/compile_downloaded_reports.py` | Compiles raw downloaded reports into Financial Report format |
| `internal/generate_monthly_distribution_reports.py` | Batch driver - processes all properties in a month folder |
| `internal/generate_distribution_report.py` | Core generator - creates a single distribution workbook |
| `internal/send_distribution_emails.py` | Email sender with dry-run support |

---

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--month` | *(required)* | Month folder name (e.g., "12. Dec") |
| `--report-date` | Auto-inferred | Report date for filenames (e.g., "12.31.25") |
| `--step` | Full workflow | Run specific step: compile, distribute, balances, email |
| `--send` | False | Actually send emails (for email step) |

---

## Output Files

For each property, the workflow generates:
- `MM.YYYY SMS - [Property] Distribution recommendation.xlsx`

Naming conventions:
- Crystal Lake → CLK in filename
- NFSS → NFSS in filename

---

## Last Updated

- **Date**: January 21, 2026
- **Changes**: Reorganized project structure with internal/ folder
