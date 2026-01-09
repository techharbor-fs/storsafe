# Cash Flow Report - Automated Builder

**Project Location**: `automation files/03. storsafe/2. Cash Flow Report/`
**Created**: October 29, 2025
**Purpose**: Programmatically generate Cash Flow Reports in Google Sheets

---

## Project Overview

This project automates the creation of Cash Flow Reports in Google Sheets by programmatically building the complete report structure with all formulas, rather than manually creating or copying reports each month.

**Key Benefit**: Creates a fully functional Cash Flow Report for any period (Aug, Sep, Oct, etc.) in seconds with consistent formula structure and no manual errors.

---

## Core Features

### 1. Report Builder (`build_cashflow_report.py`)

- Creates complete Cash Flow Report structure in Google Sheets
- Generates all VLOOKUP, SUM, and arithmetic formulas dynamically
- Supports multiple properties (columns) with property-based lookups
- Configurable GL accounts organized by cash flow category
- Applies number formatting automatically
- **Key Innovation**: Concatenated lookup keys (property + account) for O(1) data retrieval

### 2. Report Analyzer (`analyze_cashflow_report.py`)

- Analyzes existing Cash Flow Reports
- Extracts formula structure and data dependencies
- Documents calculation logic
- Exports analysis to JSON

### 3. Configuration (`cashflow_config.json`)

- Property codes (columns)
- GL account structure (Operating, Investing, Financing)
- Easy to modify without touching code

---

## Report Arrangement Logic

### Why This Structure Exists

The Cash Flow Report is **NOT just copying formulas** - it's a carefully designed data structure that enables:

1. **Dynamic Multi-Property Reporting**: Each property (2201, cpwest, ep7825) gets its own column with automatic lookups
1. **Centralized GL Account Management**: Master list defines all accounts once, reused across all periods
1. **Efficient Data Retrieval**: Concatenated keys (property+account) enable instant lookups
1. **Accounting Standard Compliance**: Structure follows indirect cash flow method (Operating, Investing, Financing)
1. **Reconciliation Built-In**: Ending balance calculation vs. bank balance verification

---

### Column-by-Column Purpose

**The report uses a 4-part column structure:**

```text
┌─────────────┬──────────────┬─────────────────┬───────────────────────────┐
│  Column A   │  Column B    │   Column C      │  Columns F+ (Properties)  │
│  (GL Code)  │  (Labels)    │ (Account Name)  │  (Transaction Amounts)    │
├─────────────┼──────────────┼─────────────────┼───────────────────────────┤
│ 9090-0000   │              │ NET INCOME      │ =VLOOKUP(F2&A4,...)       │
│ 1300-0000   │              │ Accts Receivable│ =VLOOKUP(F2&A5,...)       │
│ ...         │              │ ...             │ ...                       │
│             │ Subtotal:    │                 │ =SUM(F4:F17)              │
└─────────────┴──────────────┴─────────────────┴───────────────────────────┘
```

#### Column A: GL Account Codes (The Identifier Layer)

**Purpose**: Unique identifiers for each line item
**Content**: GL account codes (e.g., 9090-0000, 1300-0000)
**Why Static**: These codes are the foundation - they define WHAT transactions to look up
**Pattern**: Follows accounting chart structure (Assets 1xxx, Liabilities 2xxx, Income 9xxx)

#### Column B: Section Headers (The Navigation Layer)

**Purpose**: Mark major sections and subtotals
**Content**: "I. Operating Activities", "Net Cash Inflow...", etc.
**Why Important**: Provides visual structure and houses subtotal labels
**Pattern**: Appears on first row of each section and subtotal rows

#### Column C: Account Names (The Translation Layer)

**Purpose**: Convert GL codes to human-readable names
**Content**: VLOOKUP formulas that return account descriptions
**Formula Pattern**:

```excel
=arrayformula(trim(ifna(vlookup(A4:A17,{'Cash Flow (Jul)'!$A:$B},2,false),)))
```

**Why ARRAYFORMULA**: Single formula covers 14 rows (efficiency)
**Data Source**: `Cash Flow ({period})` sheet - master GL account list

**Critical Insight**: Column C is the ONLY place where GL codes get translated to names. This centralization ensures consistency.

#### Columns F+ : Property Data (The Transaction Layer)

**Purpose**: Show transaction amounts for each property
**Content**: VLOOKUP formulas with concatenated keys
**Formula Pattern**:

```excel
=arrayformula(if($C$4:$C$17="",,ifna(vlookup(F2&$A$4:$A$17,{'Support - Jul'!$A:$B:$C},2,false),0)))
```

**Breaking Down the Logic**:

1. `F2` = Property code from header (e.g., "cpwest")
1. `&$A$4:$A$17` = Concatenate with GL accounts in Column A
1. Result: "cpwest9090-0000", "cpwest1300-0000", etc.
1. VLOOKUP finds this key in `Support - {period}` sheet
1. Returns transaction amount or 0 if not found

**Why This Design Works**:

- ✅ **Fast**: O(1) lookup instead of filtering two columns
- ✅ **Scalable**: Add property = add column, no formula changes
- ✅ **Robust**: Missing transactions return 0 (not #N/A errors)
- ✅ **Flexible**: Each property independent

---

### Account Arrangement Within Sections

**The GL accounts are NOT randomly ordered - they follow accounting logic:**

#### Operating Activities (Rows 4-17)

**Logic**: Start with Net Income, then adjust for working capital changes

```text
9090-0000  NET INCOME              ← Starting point (from Income Statement)
────────── Working Capital Changes ─────────────────────────────────────
1300-0000  Accounts Receivable     ← Current Assets (increase = cash out)
1350-xxxx  Prepaid Expenses        ← Current Assets grouped together
2200-0000  Accounts Payable        ← Current Liabilities (increase = cash in)
2210-0000  Prepaid Rent           ← Current Liabilities grouped together
2250-xxxx  Deposits               ← Current Liabilities continued
2305-0000  Tax Accrual            ← Accrued Liabilities
2310-0000  Sales Tax              ← Accrued Liabilities continued
2609-0000  Interest Accrual       ← Accrued Liabilities continued
2640-xxxx  Expense/Payroll Accrual ← Accrued Liabilities continued
```

**Pattern**: Balance sheet order (Assets → Liabilities)
**Why**: Matches how accountants think about working capital

#### Investing Activities (Rows 21-29)

**Logic**: Capital expenditures and long-term asset changes

```text
1600-xxxx  Fixed Assets            ← Property, Plant, Equipment purchases
```

**Pattern**: Asset acquisition/disposal accounts
**Why**: Represents cash used for long-term investments

#### Financing Activities (Rows 33-51)

**Logic**: Debt, equity, and distribution transactions

```text
2100-xxxx  Short-term Loans        ← Current debt
2110-xxxx  Lines of Credit         ← Current debt continued
2120-xxxx  Loan Payable            ← Long-term debt
3003-xxxx  Capital Contributions   ← Equity inflows
3011-xxxx  Distributions           ← Equity outflows
3048-xxxx  Additional Distributions ← Equity outflows continued
```

**Pattern**: Debt accounts first, then equity accounts
**Why**: Shows sources and uses of capital

---

### Why Sections End with Subtotals

**Each section has a subtotal row** (Operating: Row 18, Investing: Row 30, Financing: Row 52)

**Formula Pattern**:

```excel
=sum(F4:F17)  # Sum all line items in section
```

**Purpose**:

1. **Summary Level View**: See net cash impact per activity type
1. **Reference Points**: Summary section references these subtotals
1. **Validation**: Subtotals should tie to detail
1. **Financial Statement Logic**: Matches standard cash flow statement format

---

### Dynamic Nature of the Structure

**What Makes This "Dynamic":**

1. **Add Property → Just Add Column**:
   - Put property code in Row 2
   - Formula automatically concatenates with Column A accounts
   - No manual formula editing needed

1. **Change Period → Update Sheet References**:
   - `'Cash Flow (Jul)'` → `'Cash Flow (Aug)'`
   - `'Support - Jul'` → `'Support - Aug'`
   - All formulas adapt automatically

1. **Add/Remove Accounts → Modify Column A**:
   - Insert row with new GL code
   - Column C formula automatically looks up name
   - Property columns automatically look up amounts

1. **Reusable Master Data**:
   - `Cash Flow ({period})` = Reusable GL account dictionary
   - Create once, use for all periods
   - Consistency guaranteed

---

## Technical Architecture

### Report Structure

```text
Cash Flow Report
├── Header (Row 2)
│   ├── Report Title
│   └── Property Columns (2201, cpwest, ep7825, etc.)
├── I. Operating Activities (Rows 3-18)
│   ├── NET INCOME (9090-0000)
│   ├── Working Capital Adjustments (1300-0000, 2200-0000, etc.)
│   └── Subtotal: Net Cash from Operating
├── Adjusted Cash Flow (Row 19)
│   └── Operating + Select Financing Items
├── II. Investing Activities (Rows 20-30)
│   ├── Capital Expenditures (1600-xxxx)
│   └── Subtotal: Net Cash from Investing
├── III. Financing Activities (Rows 32-52)
│   ├── Loans (2100-xxxx, 2110-xxxx, etc.)
│   ├── Capital Contributions (3003-xxxx)
│   ├── Distributions (3011-xxxx, 3048-xxxx, etc.)
│   └── Subtotal: Net Cash from Financing
├── Other Accounts (Rows 54-55)
│   ├── Interest Reserve (1200-0001)
│   └── Operating Reserve (1200-0003)
└── Summary Section (Rows 59-70)
    ├── Total Cash Flow (sum of 3 activities)
    ├── Beginning Cash Balance
    ├── Ending Cash Balance
    ├── Bank Balance (VLOOKUP to 1190-0000)
    └── Reconciliation Difference (should be $0)
```

---

## Data Flow Logic

### Stage 1: Account Label Lookup (Column C)

**Formula Pattern**:

```excel
=arrayformula(trim(ifna(vlookup(A4:A17,{'Cash Flow (Period)'!$A$1:$A,'Cash Flow (Period)'!$B$1:$B},2,false),)))
```

**What it does**:

1. Takes GL account codes from Column A (e.g., "9090-0000", "1300-0000")
1. Looks up in `Cash Flow ({period})` sheet (master GL account list)
1. Returns account descriptions (e.g., "NET INCOME", "Accounts Receivable")
1. Uses ARRAYFORMULA to process multiple rows efficiently

**Source Sheet Required**: `Cash Flow ({period})`

```text
Column A: GL Account Code (9090-0000, 1300-0000, etc.)
Column B: Account Description (NET INCOME, Accounts Receivable, etc.)
```

---

### Stage 2: Transaction Amount Lookup (Property Columns F-M+)

**Formula Pattern**:

```excel
=arrayformula(if($C$4:$C$17="",,ifna(vlookup(F2&$A$4:$A$17,{'Support - Period'!$A$2:$A&'Support - Period'!$B$2:$B,'Support - Period'!$C$2:$C},2,false),0)))
```

**What it does**:

1. **Concatenates** property code (F2) + GL account (A4)
   - Example: "cpwest" & "9090-0000" = "cpwest9090-0000"
1. **Looks up** concatenated key in `Support - {period}` sheet
1. **Returns** transaction amount for that property + account combination
1. **Returns 0** if no transaction exists (using IFNA)
1. **Skips lookup** if account name is empty (using IF condition)
1. **Uses ARRAYFORMULA** for efficiency across multiple rows

**Source Sheet Required**: `Support - {period}`

```text
Column A: Property Code (cpwest, ep7825, epcpss, etc.)
Column B: GL Account Code (9090-0000, 1300-0000, etc.)
Column C: Transaction Amount (numeric)
```

**Key Design**: Concatenated lookup key allows fast retrieval of specific (property, account) pairs

---

### Stage 3: Section Subtotals

**Formula Pattern**:

```excel
=sum(F4:F17)  # Operating Activities
=sum(F21:F29) # Investing Activities
=sum(F33:F51) # Financing Activities
```

**What it does**:

- Sums all line items within each section
- Each property column has its own subtotal
- Provides section-level cash flow view

---

### Stage 4: Adjusted Cash Flow Calculation

**Formula Pattern**:

```excel
=G18+G34+G35+G36+G37+G38
```

**What it does**:

- Combines Operating Activities subtotal (Row 18)
- With specific Financing line items (Rows 34-38)
- Provides alternative operating performance view
- Adjusts for specific financing activities

---

### Stage 5: Total Cash Flow Summary

**Components**:

1. **Section References** (Rows 61-63):

```excel
=F18  # Operating Activities
=F30  # Investing Activities
=F52  # Financing Activities
```

1. **Total Net Cash Flow** (Row 64):

```excel
=SUM(F61:F63)
```

1. **Beginning Balance** (Row 66):

```excel
=arrayformula(if(F2="",,0))  # Placeholder (currently 0)
```

1. **Net Change** (Row 67):

```excel
=F64  # Reference to total cash flow
```

1. **Ending Cash Balance** (Row 68):

```excel
=round(F66+F67,2)  # Beginning + Net Change
```

1. **Bank Balance Verification** (Row 69):

```excel
=arrayformula(round(ifna(vlookup(F2&"1190-0000",{'Support - Period'!$E$2:$E&'Support - Period'!$F$2:$F,'Support - Period'!$G$2:$G},2,false),0)+...,2))
```

- Looks up actual bank balance for account 1190-0000
- Uses alternative column structure (E-G) in Support sheet

1. **Reconciliation Difference** (Row 70):

```excel
=F68-F69  # Calculated - Actual (should be $0)
```

---

## Implementation Logic

### How `build_cashflow_report.py` Works

#### Step 1: Initialize Builder

```python
builder = CashFlowReportBuilder(
    sheet_id="YOUR_SHEET_ID",
    period="Aug",
    service_account_path=Path("task-automation.json")
)
```

#### Step 2: Create/Clear Worksheet

- Check if sheet exists (by name)
- If exists: Clear all content
- If not: Create new worksheet with sufficient rows/columns

#### Step 3: Build Header Section

- Row 1: Empty
- Row 2: Report title + property names

```python
header_row = ['', 'Cash Flow Report (Aug 2025)', '', '', ''] + properties
```

#### Step 4: Build Operating Activities Section

1. Write GL account codes to Column A
1. Generate Column C formula (account name lookup):

   ```python
   formula = f"=arrayformula(trim(ifna(vlookup(A{start}:A{end}," +
            f"{{'Cash Flow ({period})'!$A$1:$A,'Cash Flow ({period})'!$B$1:$B}},2,false),)))"
   ```

1. Generate property column formulas (transaction lookup):

   ```python
   formula = f"=arrayformula(if($C${start}:$C${end}=\"\",,ifna(vlookup({col}2&$A${start}:$A${end}," +
            f"{{'Support - {period}'!$A$2:$A&'Support - {period}'!$B$2:$B,'Support - {period}'!$C$2:$C}},2,false),0)))"
   ```

1. Add subtotal row with SUM formulas

#### Step 5: Build Investing Activities Section

- Same pattern as Operating
- Different GL accounts (1600-xxxx series)
- Own subtotal row

#### Step 6: Build Financing Activities Section

- Same pattern as Operating
- Different GL accounts (2100-xxxx, 3003-xxxx series)
- Own subtotal row

#### Step 7: Build Adjusted Cash Flow Row

```python
formula = f"={col}{operating_row}+{col}34+{col}35+{col}36+{col}37+{col}38"
```

#### Step 8: Build Summary Section

- Reference formulas to section subtotals
- SUM formula for total cash flow
- Arithmetic formulas for ending balance
- VLOOKUP for bank balance
- Difference calculation

#### Step 9: Apply Formatting

- Number format for property columns: `#,##0`
- Applied to rows 4-70, columns F onwards

---

## Prerequisites

### Required Source Sheets

#### 1. GL Account Master List: `Cash Flow ({period})`

**Purpose**: Maps account codes to descriptions

**Structure**:
| Column A | Column B |
|----------|----------|
| 9090-0000 | NET INCOME |
| 1300-0000 | Accounts Receivable |
| 1350-0001 | Pre-Paid Insurance |
| 2200-0000 | Accounts Payable |
| ... | ... |

**Notes**:

- Must include ALL accounts used in report
- Account codes must match exactly
- Created once, reused for all periods

#### 2. Transaction Data: `Support - {period}`

**Purpose**: Stores actual transaction amounts

**Structure (Primary - Columns A-C)**:
| Column A | Column B | Column C |
|----------|----------|----------|
| cpwest | 9090-0000 | 33185 |
| ep7825 | 9090-0000 | -2044 |
| cpwest | 1300-0000 | -4335 |
| epcpss | 1300-0000 | -2345 |
| ... | ... | ... |

**Structure (Bank Balance - Columns E-G)**:
| Column E | Column F | Column G |
|----------|----------|----------|
| cpwest | 1190-0000 | 50000 |
| ep7825 | 1190-0000 | 25000 |
| ... | ... | ... |

**Notes**:

- One row per (property, account) pair
- Concatenation: Property + Account = lookup key
- Bank accounts (1190-xxxx) use alternative columns
- Created for each period (Aug, Sep, Oct, etc.)

---

## Usage

### Create New Cash Flow Report

```bash
# Navigate to project folder
cd "c:\Users\jayry\python projects\automation files\03. storsafe\2. Cash Flow Report"

# Run builder script
python build_cashflow_report.py --sheet-id YOUR_SHEET_ID --period Aug
```

### Command Options

| Option | Required | Description | Example |
|--------|----------|-------------|---------|
| `--sheet-id` | Yes | Google Sheet ID | `1rb_pO5Zo...` |
| `--period` | No | Period name (default: "Aug") | `Aug`, `Sep`, `Oct` |
| `--sheet-name` | No | Custom sheet name | `"CF Report - Aug"` |
| `--no-formatting` | No | Skip number formatting | Flag only |

### Example Commands

```bash
# Create August report
python build_cashflow_report.py --sheet-id 1rb_pO5Zo5LoOs8svZX6NJgYfZdrfPkuspE89DYJ4XmY --period Aug

# Create September report with custom name
python build_cashflow_report.py --sheet-id 1rb_pO5Zo5LoOs8svZX6NJgYfZdrfPkuspE89DYJ4XmY --period Sep --sheet-name "Cash Flow - September 2025"

# Create report without formatting (faster)
python build_cashflow_report.py --sheet-id 1rb_pO5Zo5LoOs8svZX6NJgYfZdrfPkuspE89DYJ4XmY --period Oct --no-formatting
```

---

## Configuration

### Modify Properties (Columns)

Edit `cashflow_config.json`:

```json
{
  "properties": [
    "2201",
    "cpwest",
    "ep7825",
    "new-property"
  ]
}
```

### Modify GL Accounts

Edit `cashflow_config.json`:

```json
{
  "gl_accounts": {
    "operating": [
      ["9090-0000", "NET INCOME"],
      ["NEW-ACCT", "New Account Name"]
    ]
  }
}
```

### Load Configuration in Script

Add to script (if not already implemented):

```python
import json
with open('cashflow_config.json', 'r') as f:
    config = json.load(f)
builder.properties = config['properties']
builder.gl_accounts = config['gl_accounts']
```

---

## Expected Behavior

### Successful Execution

**Output Example**:

```text
================================================================================
BUILDING CASH FLOW REPORT - AUG 2025
================================================================================
Creating worksheet: Cash Flow Report (All) - Aug
  ✓ Created new sheet

📋 Building header section...
  ✓ Header row created with 15 properties

📊 Building Operating Activities section...
  ✓ Added 14 GL accounts (rows 4-17)
  ✓ Subtotal row created (row 18)

📊 Building Investing Activities section...
  ✓ Added 9 GL accounts (rows 21-29)
  ✓ Subtotal row created (row 30)

📊 Building Financing Activities section...
  ✓ Added 19 GL accounts (rows 33-51)
  ✓ Subtotal row created (row 52)

📊 Building Summary section...
  ✓ Summary section created (rows 59-67)

🎨 Applying formatting...
  ✓ Applied number formatting

================================================================================
✅ CASH FLOW REPORT BUILD COMPLETE
================================================================================

Sheet URL: https://docs.google.com/spreadsheets/d/...
Total rows used: ~68
Property columns: 15
GL accounts: 44
```

### Data Population

Once source sheets exist:

1. Account names appear in Column C (from `Cash Flow ({period})`)
1. Transaction amounts appear in property columns (from `Support - {period}`)
1. Subtotals calculate automatically
1. Summary section populates
1. Reconciliation difference (Row 70) should be $0 or near-zero

### Validation Checks

- **Row 18**: Operating Activities total
- **Row 30**: Investing Activities total
- **Row 52**: Financing Activities total
- **Row 64**: Combined total (sum of above 3)
- **Row 70**: Should be $0 (calculated ending cash = bank balance)

---

## Known Behaviors

### Good Behaviors (Keep)

- ✅ Uses ARRAYFORMULA for efficiency (reduces formula count)
- ✅ Returns 0 instead of #N/A for missing transactions
- ✅ Overwrites existing sheet (allows re-runs)
- ✅ Validates sheet name before creation
- ✅ Applies consistent number formatting
- ✅ Concatenated lookup keys enable fast retrieval
- ✅ Modular section building (easy to extend)

### Limitations

- ⚠️ Period name must match sheet names exactly (case-sensitive)
- ⚠️ Source sheets must exist before report populates
- ⚠️ GL accounts hardcoded (use config for flexibility)
- ⚠️ No built-in data validation on source sheets
- ⚠️ Adjusted Cash Flow formula references specific rows (34-38)

---

## File Structure

```text
2. Cash Flow Report/
├── build_cashflow_report.py      # Main builder script
├── analyze_cashflow_report.py    # Analysis utility
├── cashflow_config.json          # Configuration
├── PROJECT.md                     # This file
└── .helper_artifacts/            # (future) Test outputs
```

---

## Dependencies

- **Python 3.8+**: Required runtime.
- **gspread** - Google Sheets API library
- **Service Account JSON** - `task-automation.json` in project root
- **Google Sheets** - Target workbook with source sheets

---

## Future Enhancements

### Potential Improvements

1. **Dynamic source detection** - Auto-detect source sheet names
1. **Data validation** - Check source sheet structure before build
1. **Multiple periods** - Build multiple reports in one run
1. **Template inheritance** - Support custom report templates
1. **Formula verification** - Compare generated vs. expected formulas
1. **Error recovery** - Rollback on partial failures
1. **Performance optimization** - Batch API calls for faster builds
1. **Config-driven accounts** - Load GL accounts from config file
1. **Custom sections** - Allow user-defined report sections
1. **Formula testing** - Unit tests for generated formulas

---

## Troubleshooting

### Issue: Formulas show #REF! errors

**Cause**: Source sheets don't exist
**Solution**: Create `Cash Flow ({period})` and `Support - {period}` sheets first

### Issue: Values show #N/A

**Cause**: Lookup key not found in source sheet
**Solution**: Verify property+account exists in `Support - {period}`

### Issue: Sheet already exists error

**Cause**: Sheet name collision
**Solution**: Script overwrites by default, or use `--sheet-name` for custom name

### Issue: Permission denied

**Cause**: Service account lacks access
**Solution**: Share workbook with service account email

### Issue: Reconciliation difference not $0

**Cause**: Missing bank balance data or calculation error
**Solution**: Check `Support - {period}` has bank accounts (1190-0000) in columns E-G

---

## Analysis Utility

### Analyze Existing Report

```bash
python analyze_cashflow_report.py
```

**What it does**:

- Reads existing Cash Flow Report
- Extracts all formulas
- Documents calculation logic
- Identifies data sources
- Exports analysis to JSON

**Use cases**:

- Understand report structure
- Verify formula correctness
- Document calculation logic
- Troubleshoot issues

---

## Integration Notes

### With Other StorSafe Projects

This project can integrate with:

1. **Account Reconciliation** - Source data preparation
1. **Support Sheet Builders** - Upstream data pipeline
1. **Reporting Dashboard** - Downstream consumption

### Data Pipeline

```text
Transaction Sources
    ↓
Account Reconciliation (formats data)
    ↓
Support - {period} Sheet (consolidates)
    ↓
Cash Flow Report Builder (presents)
    ↓
Cash Flow Report (output)
```

---

**Last Updated**: October 29, 2025
**Maintainer**: StorSafe Automation Team
**Version**: 1.0
