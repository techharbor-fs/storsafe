"""Comprehensive review of Edge to Yardi transformation."""

import csv
import json
from pathlib import Path

BASE = Path(r"C:\Users\jvill\techharbor-fs\storsafe\09. Edge to Yardi")
MONTH_DIR = BASE / "12. Dec"
INPUT_DIR = MONTH_DIR / "Input"
OUTPUT_DIR = MONTH_DIR / "Output"

print("=" * 70)
print("  COMPREHENSIVE REVIEW - Original Folder")
print("  C:\\Users\\jvill\\techharbor-fs\\storsafe\\09. Edge to Yardi")
print("=" * 70)

# 1. Check JSON mappings
print("\n=== 1. CASH ACCOUNT MAPPINGS (JSON) ===")
json_path = INPUT_DIR / "cash_account_mappings.json"
if json_path.exists():
    data = json.load(json_path.open())
    print(f"Total properties in JSON: {len(data)}")
    print(f"ephss Credit Card - Visa: {data.get('ephss', {}).get('Credit Card - Visa', 'NOT FOUND')}")
    print(f"ephss ACH: {data.get('ephss', {}).get('ACH', 'NOT FOUND')}")
    print(f"ephss Cash: {data.get('ephss', {}).get('Cash', 'NOT FOUND')}")
else:
    print(f"ERROR: JSON file not found at {json_path}")

# 2. Check output files exist
print("\n=== 2. OUTPUT FILES ===")
jay_files = list(OUTPUT_DIR.glob("yardi_import__*__2025-12.csv"))
print(f"Individual property files: {len(jay_files)}")

compiled = OUTPUT_DIR / "yardi_import_compiled__2025-12.csv"
jay_combined = OUTPUT_DIR / "yardi_import_Jay__2025-12.csv"
corrections = OUTPUT_DIR / "cash_account_corrections__2025-12.csv"

print(f"Compiled all: {'EXISTS' if compiled.exists() else 'MISSING'}")
print(f"Jay combined: {'EXISTS' if jay_combined.exists() else 'MISSING'}")
print(f"Corrections report: {'EXISTS' if corrections.exists() else 'MISSING'}")

# 3. Verify ephss individual file
print("\n=== 3. EPHSS INDIVIDUAL FILE CHECK ===")
ephss_file = OUTPUT_DIR / "yardi_import__ephss__2025-12.csv"
if ephss_file.exists():
    with ephss_file.open("r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    
    credit_card_rows = [r for r in rows if len(r) > 14 and "Credit Card" in r[14]]
    ach_rows = [r for r in rows if len(r) > 14 and r[14] == "ACH"]
    
    print(f"Total rows: {len(rows)}")
    print(f"Credit Card rows: {len(credit_card_rows)}")
    print(f"ACH rows: {len(ach_rows)}")
    
    # Check account codes
    cc_codes = set(r[10] for r in credit_card_rows)
    ach_codes = set(r[10] for r in ach_rows)
    
    print(f"Credit Card account codes used: {cc_codes}")
    print(f"ACH account codes used: {ach_codes}")
    
    if cc_codes == {"1110-4977"}:
        print("[OK] All Credit Card rows have correct code 1110-4977")
    else:
        print(f"[ERROR] Found wrong codes in Credit Card rows!")
    
    if ach_codes == {"1110-4977"} or len(ach_codes) == 0:
        print("[OK] All ACH rows have correct code 1110-4977 (or no ACH)")
    else:
        print(f"[ERROR] Found wrong codes in ACH rows!")
else:
    print(f"ERROR: File not found at {ephss_file}")

# 4. Verify Jay combined file matches individual
print("\n=== 4. JAY COMBINED FILE - EPHSS CHECK ===")
if jay_combined.exists():
    with jay_combined.open("r", encoding="utf-8-sig") as f:
        jay_rows = list(csv.reader(f))
    
    ephss_in_jay = [r for r in jay_rows if len(r) > 8 and r[8] == "ephss"]
    ephss_cc_in_jay = [r for r in ephss_in_jay if len(r) > 14 and "Credit Card" in r[14]]
    
    print(f"Total rows in Jay combined: {len(jay_rows)}")
    print(f"EPHSS rows in Jay combined: {len(ephss_in_jay)}")
    print(f"EPHSS Credit Card rows: {len(ephss_cc_in_jay)}")
    
    jay_cc_codes = set(r[10] for r in ephss_cc_in_jay)
    print(f"EPHSS Credit Card codes in Jay file: {jay_cc_codes}")
    
    if jay_cc_codes == {"1110-4977"}:
        print("[OK] Jay combined has correct code 1110-4977 for ephss Credit Cards")
    else:
        print(f"[ERROR] Wrong codes in Jay combined file!")

# 5. Compare individual vs compiled
print("\n=== 5. CONSISTENCY CHECK (Individual vs Compiled) ===")
if ephss_file.exists() and jay_combined.exists():
    with ephss_file.open("r", encoding="utf-8-sig") as f:
        individual_rows = list(csv.reader(f))
    
    with jay_combined.open("r", encoding="utf-8-sig") as f:
        compiled_rows = list(csv.reader(f))
    
    # Find ephss rows in compiled
    compiled_ephss = [r for r in compiled_rows if len(r) > 8 and r[8] == "ephss"]
    
    if len(individual_rows) == len(compiled_ephss):
        # Compare each row
        mismatches = 0
        for i, (ind, comp) in enumerate(zip(individual_rows, compiled_ephss)):
            if ind != comp:
                mismatches += 1
                if mismatches <= 3:
                    print(f"  Mismatch at row {i+1}:")
                    print(f"    Individual: {ind[10] if len(ind) > 10 else 'N/A'}")
                    print(f"    Compiled:   {comp[10] if len(comp) > 10 else 'N/A'}")
        
        if mismatches == 0:
            print(f"[OK] Individual and compiled files are IDENTICAL ({len(individual_rows)} rows)")
        else:
            print(f"[ERROR] Found {mismatches} mismatches!")
    else:
        print(f"[ERROR] Row count mismatch: Individual={len(individual_rows)}, Compiled={len(compiled_ephss)}")

# 6. Check corrections report
print("\n=== 6. CORRECTIONS REPORT ===")
if corrections.exists():
    with corrections.open("r", encoding="utf-8-sig") as f:
        corr_rows = list(csv.DictReader(f))
    
    print(f"Total corrections: {len(corr_rows)}")
    
    ephss_corr = [r for r in corr_rows if r["property_code"] == "ephss"]
    print(f"EPHSS corrections: {len(ephss_corr)}")
    
    if ephss_corr:
        # Check direction of corrections
        wrong_direction = [r for r in ephss_corr if r["corrected_code"] == "1110-4328"]
        right_direction = [r for r in ephss_corr if r["corrected_code"] == "1110-4977"]
        
        print(f"  Corrected TO 1110-4977 (correct): {len(right_direction)}")
        print(f"  Corrected TO 1110-4328 (WRONG): {len(wrong_direction)}")
        
        if wrong_direction:
            print("[ERROR] Some corrections went in wrong direction!")
        else:
            print("[OK] All corrections are in correct direction")

print("\n" + "=" * 70)
print("  REVIEW COMPLETE")
print("=" * 70)
