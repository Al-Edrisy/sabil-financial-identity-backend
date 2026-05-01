import sys
sys.path.insert(0, '.')
from app.services.statement_service import StatementService

# Simulate the exact format in the .txt test files
lines = [
    "('2026-01-01', 'Salary January', 2500, 'USD')",
    "('2026-01-03', 'Supermarket', -120, 'USD')",
    "('2026-01-05', 'Electricity Bill', -80, 'USD')",
    "('2026-01-10', 'Freelance Payment', 600, 'USD')",
    "('2026-01-15', 'Rent', -700, 'USD')",
]

normalized = StatementService._normalize_text_lines(lines)
print("Normalized lines:")
for l in normalized:
    print(f"  {l!r}")

# Test the full parse pipeline
from app.ai.parsing.transaction_parser import parse_transactions
rows = parse_transactions(normalized)
print(f"\nParsed {len(rows)} transactions:")
for r in rows:
    print(f"  {r.type:8s} | {r.amount:8.2f} {r.currency} | {r.description}")
