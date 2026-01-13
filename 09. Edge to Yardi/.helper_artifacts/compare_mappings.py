"""Compare old CSV mapping vs new JSON mapping to find wrong uploads."""

import csv
import json
from pathlib import Path

# Paths
base = Path(__file__).resolve().parent.parent
csv_path = base / "12. Dec" / "Input" / "property_cash_account_mapping.csv"
json_path = base / "12. Dec" / "Input" / "cash_account_mappings.json"

# Load old CSV mapping
old_mapping = {}
with csv_path.open("r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        prop = row.get("property_code", "").strip().lower()
        code = row.get("correct_cash_account", "").strip()
        if prop and code:
            old_mapping[prop] = code

# Load new JSON mapping
with json_path.open("r") as f:
    new_mapping = json.load(f)

# Compare - find properties where Credit Card codes differ
print("Properties with DIFFERENT cash account mappings (Credit Card - Visa):")
print("=" * 70)
print(f"{'Property':<15} {'OLD (CSV)':<15} {'NEW (Sheet)':<15} {'STATUS'}")
print("-" * 70)

mismatched = []
for prop in sorted(set(old_mapping.keys()) | set(new_mapping.keys())):
    old_code = old_mapping.get(prop, "N/A")
    new_codes = new_mapping.get(prop, {})
    new_cc_visa = new_codes.get("Credit Card - Visa", "N/A")
    
    if old_code != new_cc_visa and old_code != "N/A" and new_cc_visa != "N/A":
        mismatched.append(prop)
        print(f"{prop:<15} {old_code:<15} {new_cc_visa:<15} ** WRONG **")

print()
print(f"TOTAL PROPERTIES WITH WRONG UPLOADS: {len(mismatched)}")
print()
if mismatched:
    print("Affected property codes:")
    for prop in mismatched:
        print(f"  - {prop}")
