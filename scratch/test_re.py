import re

TUPLE_RE = re.compile(
    r"\(\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?\s*,"
    r"\s*['\"]([^'\"]+)['\"]\s*,"
    r"\s*(-?[\d.]+)\s*,"
    r"\s*['\"]([A-Z]{3})['\"]\s*\)",
    re.IGNORECASE,
)

line = "(\"2026-01-01\", \"Salary\", 1500, \"USD\")"
m = TUPLE_RE.search(line)
if m:
    print(f"Matched: {m.groups()}")
else:
    print("No match")
