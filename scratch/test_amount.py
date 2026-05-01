import sys
sys.path.insert(0, '.')
from app.ai.parsing.currency_normalizer import extract_amount_and_currency
print(extract_amount_and_currency("2026-01-01,Salary,1500,USD"))
