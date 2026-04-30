from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Sabil — Financial Identity"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # SECURITY
    SECRET_KEY: str = "super-secret-key-for-dev"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    # DATABASE
    # Automatically convert postgresql:// to postgresql+asyncpg:// if needed
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sabil"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # CORS — accepts a comma-separated string from env or a JSON list
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS into a list for CORSMiddleware."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # FIREBASE
    FIREBASE_CREDENTIALS_PATH: str = "firebase-credentials.json"

    # KYC file storage
    KYC_UPLOAD_DIR: str = "uploads/kyc"

    # ── KYC evaluation thresholds ────────────────────────────────────────
    # Face match: VGG-Face cosine distances for real same-person pairs are
    # often in the 0.3–0.5 range. Threshold >=0.5 for auto-approval, >=0.25
    # for PENDING (human review).
    # OpenCV fallback scores are lower — 0.45 is a safe auto-approve threshold.
    KYC_FACE_MATCH_THRESHOLD:        float = 0.45   # auto-approve (OpenCV: ~0.5–0.7 for same person)
    KYC_FACE_MATCH_MANUAL_THRESHOLD: float = 0.20   # PENDING for human review
    KYC_LIVENESS_MIN_VARIANCE:       float = 60.0   # was 80.0 — lower for real-world images
    KYC_REQUIRE_LIVENESS:            bool  = False   # off by default until TF backend is stable
    KYC_MAX_RESUBMISSIONS:           int   = 5       # was 3 — allow more attempts
    KYC_EXPIRY_DAYS:                 int   = 365
    KYC_OCR_MIN_CONFIDENCE:          float = 0.30    # was 0.35 — more permissive for Arabic
    KYC_LIVENESS_FREQ_THRESHOLD:     float = 0.5
    KYC_LIVENESS_MANUAL_THRESHOLD:   float = 40.0    # was 60.0 — lower bar for PENDING
    STORAGE_BACKEND: str = "local"
    KYC_WEBHOOK_URL: str = ""

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = ""

    # ── Webhooks ─────────────────────────────────────────────────────────────
    WEBHOOK_SECRET: str = ""          # HMAC-SHA256 signing key for outbound webhooks
    CREDIT_WEBHOOK_URL: str = ""      # POST endpoint for credit score change events

    # ── Credit Scoring ───────────────────────────────────────────────────────
    CREDIT_UPLOAD_DIR: str = "uploads/statements"
    CREDIT_SCORE_MIN_TRANSACTIONS: int = 1   # 1 transaction is enough for a partial score
    CREDIT_SCORE_INCOME_CAP: float = 50000.0
    CREDIT_CATEGORIZER_THRESHOLD: int = 70

    class Config:
        case_sensitive = True

settings = Settings()
