import os
from cryptography.fernet import Fernet
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Use a secret key from environment or generate a default one (only for dev!)
# For production, this MUST be set in environment variables.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    logger.warning("ENCRYPTION_KEY not found in environment. Sensitive data encryption will be degraded.")
    # In a real app, you might want to raise an error or use a fallback for dev only
    _key = Fernet.generate_key()
    fernet = Fernet(_key)
else:
    try:
        fernet = Fernet(ENCRYPTION_KEY.encode())
    except Exception as e:
        logger.error(f"Invalid ENCRYPTION_KEY: {e}")
        raise ValueError("Invalid ENCRYPTION_KEY configuration")

def encrypt_data(data: str) -> str:
    """
    Encrypt a string using Fernet symmetric encryption.
    """
    if not data:
        return data
    try:
        return fernet.encrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return data

def decrypt_data(token: str) -> str:
    """
    Decrypt a Fernet token back to plain text.
    """
    if not token:
        return token
    try:
        return fernet.decrypt(token.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return token
