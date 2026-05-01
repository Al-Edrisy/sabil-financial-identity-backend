from app.ai.parsing.transaction_parser import parse_transactions

lines = [
    "('2026-01-01', 'Salary January', 2500, 'USD')",
    "('2026-01-03', 'Supermarket', -120, 'USD')"
]

rows = parse_transactions(lines)
print(f"Tuple format: {len(rows)} rows")

lines2 = [
    "2026-01-01 Salary January 2500 USD",
    "2026-01-03 Supermarket -120 USD"
]
rows2 = parse_transactions(lines2)
print(f"Plain format: {len(rows2)} rows")
