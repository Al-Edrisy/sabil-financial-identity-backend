import random
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models.user import User
from app.models.parsed_transaction import ParsedTransaction, ParsedTransactionType, ParsedTransactionSource
from app.models.wallet import Wallet
from app.models.kyc import KYC, KYCStatus
from app.models.transaction import Transaction
from app.models.credit_score import CreditScore
from app.core.logger import get_logger

logger = get_logger(__name__)

GOOD_USER_TX = [
    ("2026-01-01", "Salary January", 2500, "USD"),
    ("2026-01-03", "Supermarket", -120, "USD"),
    ("2026-01-05", "Electricity Bill", -80, "USD"),
    ("2026-01-10", "Freelance Payment", 600, "USD"),
    ("2026-01-15", "Rent", -700, "USD"),
    ("2026-01-18", "Coffee", -15, "USD"),
    ("2026-01-22", "Online Shopping", -200, "USD"),
    ("2026-01-28", "Savings Transfer", -500, "USD"),
    ("2026-02-01", "Salary February", 2500, "USD"),
    ("2026-02-05", "Supermarket", -130, "USD"),
    ("2026-02-10", "Freelance Payment", 550, "USD"),
    ("2026-02-15", "Rent", -700, "USD"),
    ("2026-02-20", "Restaurant", -90, "USD"),
]

AVG_USER_TX = [
    ("2026-01-01", "Salary", 1500, "USD"),
    ("2026-01-03", "Groceries", -200, "USD"),
    ("2026-01-05", "Rent", -600, "USD"),
    ("2026-01-10", "Freelance", 200, "USD"),
    ("2026-01-12", "Shopping", -250, "USD"),
    ("2026-01-15", "Utilities", -120, "USD"),
    ("2026-01-18", "Restaurant", -100, "USD"),
    ("2026-01-25", "Savings", -100, "USD"),
]

BAD_USER_TX = [
    ("2026-01-02", "Cash Deposit", 300, "USD"),
    ("2026-01-03", "Fast Food", -50, "USD"),
    ("2026-01-04", "Online Gambling", -200, "USD"),
    ("2026-01-06", "Loan Payment", -400, "USD"),
    ("2026-01-07", "Unknown Expense", -150, "USD"),
    ("2026-01-10", "Cash Deposit", 250, "USD"),
    ("2026-01-12", "Shopping", -300, "USD"),
    ("2026-01-15", "Loan Payment", -400, "USD"),
    ("2026-01-20", "Fast Food", -80, "USD"),
]

async def seed_test_users(session):
    configs = [
        {
            "email": "good_user@test.com",
            "phone": "+96742424242",
            "name": "Seed User (Good)",
            "txs": GOOD_USER_TX,
            "score": 780,
            "risk": "trusted",
        },
        {
            "email": "average_user@test.com",
            "phone": "+967111111111",
            "name": "Average User",
            "txs": AVG_USER_TX,
            "score": 620,
            "risk": "moderate",
        },
        {
            "email": "bad_user@test.com",
            "phone": "+967222222222",
            "name": "Bad User",
            "txs": BAD_USER_TX,
            "score": 450,
            "risk": "risky",
        }
    ]

    for cfg in configs:
        # Check if user already exists
        res = await session.execute(select(User).where(User.phone_number == cfg["phone"]))
        existing_user = res.scalar_one_or_none()
        if existing_user:
            logger.info(f"User {cfg['phone']} already exists, skipping seed.")
            continue

        logger.info(f"Seeding user {cfg['phone']}...")
        user = User(
            email=cfg["email"],
            phone_number=cfg["phone"],
            full_name=cfg["name"],
            is_active=True,
            onboarding_step=3,
            phone_verified=True,
            country_code="YE"
        )
        session.add(user)
        await session.flush()

        wallet = Wallet(user_id=user.id, balance=1000.0, currency="USD")
        session.add(wallet)

        from app.core.security import pii_security
        
        id_number_plain = f"ID-{random.randint(10000, 99999)}"
        kyc = KYC(
            user_id=user.id,
            status=KYCStatus.VERIFIED,
            id_type="National ID",
            id_number=pii_security.encrypt(id_number_plain),
            id_number_hash=pii_security.blind_index(id_number_plain),
            full_name=pii_security.encrypt(cfg["name"]),
            nationality=pii_security.encrypt("Yemeni"),
            country=pii_security.encrypt("Yemen"),
            dob=pii_security.encrypt("1990-01-01"),
            gender="M", # not encrypted based on model
            document_expires_at=datetime.now() + timedelta(days=365)
        )
        session.add(kyc)

        for date_str, desc, amount, curr in cfg["txs"]:
            tx_type = ParsedTransactionType.INCOME if amount > 0 else ParsedTransactionType.EXPENSE
            pt = ParsedTransaction(
                user_id=user.id,
                upload_id=f"seed_upload_{user.id}",
                description=desc,
                amount=abs(amount),
                normalized_amount=abs(amount),
                currency=curr,
                type=tx_type,
                transaction_date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                source=ParsedTransactionSource.MANUAL,
                confidence=1.0
            )
            session.add(pt)

        cs = CreditScore(
            user_id=user.id,
            score=cfg["score"],
            risk_level=cfg["risk"],
            income_level=85.0 if cfg["risk"] == "trusted" else 40.0,
            is_active=True,
            data_quality="good",
            transaction_count=len(cfg["txs"])
        )
        session.add(cs)

    await session.commit()
    logger.info("Test data seeding complete.")
