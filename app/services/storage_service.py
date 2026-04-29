"""
app/services/storage_service.py — Pluggable file storage backend.

Backends:
  LocalStorage — writes to local filesystem (default, dev/staging)
  S3Storage    — scaffold for AWS S3 (production)

Usage:
  from app.services.storage_service import get_storage
  store = get_storage()          # KYC uploads
  store = get_storage("credit")  # Statement uploads
"""

from pathlib import Path
from typing import Protocol, Literal
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------
class StorageBackend(Protocol):
    def save(self, content: bytes, filename: str) -> str: ...
    def delete(self, path: str) -> None: ...
    def get_url(self, path: str) -> str: ...


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------
class LocalStorage:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, filename: str) -> str:
        dest = self.upload_dir / filename
        dest.write_bytes(content)
        logger.debug(f"LocalStorage: saved {filename} ({len(content)} bytes)")
        return str(dest)

    def delete(self, path: str) -> None:
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                logger.info(f"LocalStorage: deleted {path}")
        except Exception as e:
            logger.error(f"LocalStorage: failed to delete {path}: {e}")

    def get_url(self, path: str) -> str:
        return path


# ---------------------------------------------------------------------------
# S3 backend (scaffold)
# ---------------------------------------------------------------------------
class S3Storage:
    """Scaffold for AWS S3 integration. Implement with boto3 in production."""

    def save(self, content: bytes, filename: str) -> str:
        logger.warning("S3Storage.save() not implemented — using local simulation")
        return f"s3://bucket/{filename}"

    def delete(self, path: str) -> None:
        logger.warning(f"S3Storage.delete({path}) not implemented")

    def get_url(self, path: str) -> str:
        return f"https://s3.amazonaws.com/bucket/{path}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_storage(purpose: Literal["kyc", "credit"] = "kyc") -> StorageBackend:
    """
    Return the configured storage backend for the given purpose.

    Args:
        purpose: "kyc" uses KYC_UPLOAD_DIR, "credit" uses CREDIT_UPLOAD_DIR.
    """
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "s3":
        return S3Storage()

    upload_dir = (
        settings.CREDIT_UPLOAD_DIR if purpose == "credit" else settings.KYC_UPLOAD_DIR
    )
    return LocalStorage(upload_dir)


# Module-level singleton for KYC (backward-compatible with existing imports)
storage = get_storage("kyc")
