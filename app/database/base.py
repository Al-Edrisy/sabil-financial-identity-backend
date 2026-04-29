"""
app/database/base.py — Imports all ORM models so Alembic's autogenerate
can discover every table in a single import.

Import order matters: models with no FK dependencies first,
then models that reference them.
"""

from app.database.session import Base  # noqa: F401 — re-exported for Alembic env.py

# ── Core identity ─────────────────────────────────────────────────────────────
from app.models.user import User                          # noqa: F401
from app.models.wallet import Wallet                      # noqa: F401
from app.models.kyc import KYC                            # noqa: F401
from app.models.audit import AuditLog                     # noqa: F401

# ── Financial ledger ──────────────────────────────────────────────────────────
from app.models.transaction import Transaction            # noqa: F401

# ── Credit scoring pipeline ───────────────────────────────────────────────────
from app.models.parsed_transaction import ParsedTransaction  # noqa: F401
from app.models.credit_score import CreditScore              # noqa: F401
