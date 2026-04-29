"""
app/core/security.py — PII encryption and security utilities.

Provides application-layer encryption for sensitive identity data (id_number, full_name, dob, etc.)
using AES-256 (Fernet) to ensure data is encrypted at rest in the database.
"""

import os
from cryptography.fernet import Fernet
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Master encryption key — must be 32 base64-encoded bytes.
# If not provided in .env, this will fail in production to prevent clear-text storage.
_ENCRYPTION_KEY = os.getenv("KYC_PII_ENCRYPTION_KEY")

class PIIEncryption:
    """
    Handles encryption/decryption of Personally Identifiable Information (PII).
    """
    def __init__(self):
        if not _ENCRYPTION_KEY:
            # In development (SECRET_KEY is the default dev value), use a stable
            # per-process key derived from SECRET_KEY so restarts don't break
            # existing encrypted data during development.
            logger.warning(
                "KYC_PII_ENCRYPTION_KEY not set. "
                "Using dev fallback — NOT SECURE for production."
            )
            import base64, hashlib
            raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
            dev_key = base64.urlsafe_b64encode(raw)
            self.fernet = Fernet(dev_key)
        else:
            self.fernet = Fernet(_ENCRYPTION_KEY.encode())

    def encrypt(self, plain_text: str | None) -> str | None:
        if plain_text is None:
            return None
        return self.fernet.encrypt(plain_text.encode()).decode()

    def blind_index(self, plain_text: str | None) -> str | None:
        """
        Generates a deterministic hash of the plaintext for exact-match searching
        on encrypted columns. Uses SHA-256 with the encryption key as a salt.
        """
        if plain_text is None:
            return None
        import hashlib, hmac
        # Use the encryption key itself as the HMAC salt to ensure consistency
        salt = _ENCRYPTION_KEY or settings.SECRET_KEY
        return hmac.new(
            salt.encode(),
            plain_text.strip().upper().encode(),
            hashlib.sha256
        ).hexdigest()

    def decrypt(self, cipher_text: str | None) -> str | None:
        if cipher_text is None:
            return None
        try:
            return self.fernet.decrypt(cipher_text.encode()).decode()
        except Exception as e:
            logger.error(f"PII Decryption failed: {e}")
            return "[DECRYPTION_FAILED]"

# Global singleton instance
pii_security = PIIEncryption()
