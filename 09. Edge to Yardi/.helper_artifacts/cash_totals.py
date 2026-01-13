"""Calculate cash totals for each property."""
import csv
from pathlib import Path
from decimal import Decimal

output_dir = Path(__file__).parent.parent / "12. Dec" / "Output"
jay_props = ['ephss', 'ephss2', 'ssvenice', 'munster', 'epmss', 'ssracine', 'sspbay', 'ssmsouth', 'ssmadiso', 'sselkhar', 'ssdowven', 'sschgr', 'sscedarl', 'sscandle']

cash_keywords = ['cash', 'checks', 'ach', 'money order', 'credit card', 'refund checks']

print(f"{'Property':<12} {'Cash Total':>15} {'Rows':>8}")
print("-" * 38)

grand_total = Decimal('0')
total_rows = 0

for prop in jay_props:
    csv_path = output_dir / f"yardi_import__{prop}__2025-12.csv"
    if csv_path.exists():
        total = Decimal('0')
        count = 0
        with csv_path.open('r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) > 14:
                    desc = row[14].lower()
                    if any(kw in desc for kw in cash_keywords):
                        try:
                            amt = Decimal(row[9].replace(',', ''))
                            total += amt
                            count += 1
                        except:
                            pass
        print(f"{prop:<12} {total:>15,.2f} {count:>8}")
        grand_total += total
        total_rows += count
    else:
        print(f"{prop:<12} {'FILE NOT FOUND':>15}")

print("-" * 38)
print(f"{'TOTAL':<12} {grand_total:>15,.2f} {total_rows:>8}")
