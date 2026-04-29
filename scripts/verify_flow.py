"""scripts/verify_flow.py — Verify all 3 steps of the user flow."""
import sys
sys.path.insert(0, '.')
import app.database.base

errors = []

# ── Step 1: Auth ──────────────────────────────────────────────────────────────
try:
    from app.api.v1.routes.auth import router as auth_router
    from app.schemas.user import SendOTPRequest, VerifyOTPRequest, OTPResponse
    from app.dependencies.auth import create_access_token, get_current_user
    from app.services.auth_service import AuthService, DEV_PHONE, DEV_OTP_CODE
    assert DEV_PHONE == "+96742424242"
    assert DEV_OTP_CODE == "7744"
    print("OK  Step 1 auth — OTP endpoints, dev bypass configured")
except Exception as e:
    errors.append(f"FAIL Step 1 auth: {e}")

# ── Step 2: KYC ───────────────────────────────────────────────────────────────
try:
    from app.api.v1.routes.kyc import router as kyc_router
    from app.services.kyc_service import KYCService
    from app.models.kyc import KYC
    cols = {c.name for c in KYC.__table__.columns}
    required = {"document_issued_at", "full_name", "dob", "gender", "rejection_reason", "liveness_details", "id_number_hash"}
    missing = required - cols
    assert not missing, f"Missing KYC columns: {missing}"
    print(f"OK  Step 2 KYC — {len(cols)} columns, manual fields present")
except Exception as e:
    errors.append(f"FAIL Step 2 KYC: {e}")

# ── Step 3: Credit ────────────────────────────────────────────────────────────
try:
    from app.api.v1.routes.credit import router as credit_router
    from app.services.statement_service import StatementService
    from app.utils.document_validation import (
        validate_financial_document, extract_text_from_pdf,
        extract_text_from_csv, extract_text_from_plain,
        IMAGE_TYPES, PDF_TYPES, CSV_TYPES,
    )
    assert "application/pdf" in PDF_TYPES
    assert "text/csv" in CSV_TYPES
    print("OK  Step 3 credit — multi-format document support")
except Exception as e:
    errors.append(f"FAIL Step 3 credit: {e}")

# ── FX / Currency ─────────────────────────────────────────────────────────────
try:
    from app.utils.fx import (
        convert_currency, get_currency_for_country,
        list_supported_currencies, normalize_to_user_currency,
    )
    currencies = list_supported_currencies()
    assert len(currencies) > 40, f"Expected >40 currencies, got {len(currencies)}"
    assert get_currency_for_country("SA") == "SAR"
    assert get_currency_for_country("YE") == "YER"
    assert get_currency_for_country("TR") == "TRY"
    assert get_currency_for_country("AE") == "AED"
    assert get_currency_for_country("US") == "USD"
    usd_to_sar, rate = convert_currency(100, "USD", "SAR")
    assert abs(usd_to_sar - 375.0) < 1, f"100 USD should be ~375 SAR, got {usd_to_sar}"
    converted, home_curr, r = normalize_to_user_currency(100, "USD", "SA")
    assert home_curr == "SAR"
    # Cross-currency: TRY to SAR
    try_to_sar, _ = convert_currency(1000, "TRY", "SAR")
    assert try_to_sar > 0
    print(f"OK  FX — {len(currencies)} currencies, 100 USD = {usd_to_sar} SAR, 1000 TRY = {try_to_sar:.2f} SAR")
except Exception as e:
    errors.append(f"FAIL FX: {e}")

# ── User model ────────────────────────────────────────────────────────────────
try:
    from app.models.user import User
    cols = {c.name for c in User.__table__.columns}
    for col in ["phone_verified", "onboarding_step", "country_code"]:
        assert col in cols, f"missing {col}"
    assert User.__table__.c.email.nullable, "email should be nullable"
    assert User.__table__.c.phone_number.nullable, "phone_number should be nullable"
    assert User.__table__.c.firebase_uid.nullable, "firebase_uid should be nullable"
    print(f"OK  User model — {len(cols)} columns, nullable email/phone/firebase_uid")
except Exception as e:
    errors.append(f"FAIL User model: {e}")

# ── App factory ───────────────────────────────────────────────────────────────
try:
    from app.main import app
    routes = sorted(set(r.path for r in app.routes))
    required_routes = [
        "/api/v1/auth/send-otp",
        "/api/v1/auth/verify-otp",
        "/api/v1/auth/login",
        "/api/v1/kyc/verify",
        "/api/v1/kyc/status",
        "/api/v1/credit/upload",
        "/api/v1/credit/score",
        "/api/v1/credit/currencies",
        "/api/v1/users/me/onboarding-status",
    ]
    missing_routes = [r for r in required_routes if r not in routes]
    assert not missing_routes, f"Missing routes: {missing_routes}"
    print(f"OK  App factory — {len(routes)} routes, all required routes present")
    for r in routes:
        if any(k in r for k in ["otp", "credit", "/kyc", "onboarding"]):
            print(f"   {r}")
except Exception as e:
    errors.append(f"FAIL App: {e}")

# ── OTP dev bypass logic ──────────────────────────────────────────────────────
try:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app.services.auth_service import AuthService, _OTP_STORE

    # Simulate send_otp for dev phone
    async def test_otp():
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.commit = AsyncMock()

        svc = AuthService(mock_db)
        result = await svc.send_otp("+96742424242")
        assert result["phone_number"] == "+96742424242"
        assert _OTP_STORE.get("+96742424242", {}).get("code") == "7744"
        print("OK  OTP dev bypass — +96742424242 gets code 7744")

    asyncio.run(test_otp())
except Exception as e:
    errors.append(f"FAIL OTP dev bypass: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("All checks passed.")
