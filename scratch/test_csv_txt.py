import sys
sys.path.insert(0, '.')
from app.ai.parsing.transaction_parser import parse_transactions

lines = [
    "2026-01-01,Salary,1500,USD",
    "2026-01-03,Groceries,-200,USD"
]

rows = parse_transactions(lines)
print(f"Parsed: {len(rows)}")
for r in rows:
    print(r)
