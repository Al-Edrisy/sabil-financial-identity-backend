import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

try:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin initialized successfully.")
except Exception as e:
    logger.error(f"Error initializing Firebase Admin: {e}")

def verify_firebase_token(id_token: str):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return None
