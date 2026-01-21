#!/usr/bin/env python3
"""Quick database check script."""
import sqlite3

conn = sqlite3.connect('data/bank_rec.db')
conn.row_factory = sqlite3.Row

# Check period
periods = conn.execute('SELECT * FROM reconciliation_periods').fetchall()
print("Periods:")
for p in periods:
    print(f"  ID {p['id']}: year={p['year']}, month={p['month']}")

# Count transactions
bank_count = conn.execute('SELECT COUNT(*) FROM bank_transactions').fetchone()[0]
yardi_count = conn.execute('SELECT COUNT(*) FROM yardi_transactions').fetchone()[0]
print(f"\nBank transactions: {bank_count}")
print(f"Yardi transactions: {yardi_count}")

# Check matches
matches = conn.execute('''
    SELECT match_pass, match_type, COUNT(*) as cnt
    FROM matches
    GROUP BY match_pass, match_type
    ORDER BY match_pass
''').fetchall()
print("\nMatches by pass:")
for m in matches:
    print(f"  {m['match_pass']} ({m['match_type']}): {m['cnt']}")

# Total matched
total_matches = conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0]
print(f"\nTotal match records: {total_matches}")

# Count unmatched
unmatched_bank = conn.execute('''
    SELECT COUNT(*) FROM bank_transactions bt
    WHERE NOT EXISTS (
        SELECT 1 FROM match_bank_transactions mbt WHERE mbt.bank_transaction_id = bt.id
    )
''').fetchone()[0]
print(f"Unmatched bank: {unmatched_bank}")

unmatched_yardi = conn.execute('''
    SELECT COUNT(*) FROM yardi_transactions yt
    WHERE NOT EXISTS (
        SELECT 1 FROM match_yardi_transactions myt WHERE myt.yardi_transaction_id = yt.id
    )
''').fetchone()[0]
print(f"Unmatched yardi: {unmatched_yardi}")
