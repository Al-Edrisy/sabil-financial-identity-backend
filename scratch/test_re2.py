import re

CSV_TXT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s*,\s*([^,]+)\s*,\s*(-?[\d.]+)\s*,\s*([A-Z]{3})$",
    re.IGNORECASE,
)

m = CSV_TXT_RE.match("2026-01-01,Salary,1500,USD")
print(m.groups() if m else "No match")

m2 = CSV_TXT_RE.match("2026-01-01, Groceries , -200 , USD")
print(m2.groups() if m2 else "No match")
