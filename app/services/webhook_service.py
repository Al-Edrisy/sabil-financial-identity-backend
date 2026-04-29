"""
app/services/webhook_service.py — Outbound webhook notifications.

Sends signed POST requests to configured webhook URLs on:
  - KYC status changes   (KYC_WEBHOOK_URL)
  - Credit score changes (CREDIT_WEBHOOK_URL)

Signatures use HMAC-SHA256 with WEBHOOK_SECRET so receivers can verify
the payload hasn't been tampered with.

Header added to every request:
  X-Sabil-Signature: sha256=<hex_digest>
"""

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------
def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """
    Compute HMAC-SHA256 of *payload_bytes* using *secret*.
    Returns the hex digest prefixed with 'sha256='.
    """
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# Webhook service
# ---------------------------------------------------------------------------
class WebhookService:
    def __init__(self):
        self._kyc_url    = settings.KYC_WEBHOOK_URL or None
        self._credit_url = getattr(settings, "CREDIT_WEBHOOK_URL", None) or None
        self._secret     = getattr(settings, "WEBHOOK_SECRET", "") or ""

    async def _send(self, url: str, payload: Dict[str, Any]) -> None:
        """
        POST *payload* as JSON to *url* with an HMAC-SHA256 signature header.
        Failures are logged but never raised — webhooks must not block the
        main request lifecycle.
        """
        try:
            body = json.dumps(payload, default=str).encode("utf-8")
            headers: Dict[str, str] = {
                "Content-Type": "application/json",
                "X-Sabil-Timestamp": str(int(time.time())),
            }
            if self._secret:
                headers["X-Sabil-Signature"] = _sign_payload(body, self._secret)

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, content=body, headers=headers)
                response.raise_for_status()
                logger.info(
                    f"Webhook sent to {url} "
                    f"[status={response.status_code} event={payload.get('event')}]"
                )
        except Exception as exc:
            logger.error(f"Webhook delivery failed to {url}: {exc}")

    # ── KYC ──────────────────────────────────────────────────────────────────

    async def notify_kyc_status_change(
        self,
        user_id: int,
        status: str,
        attempt_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Fire a KYC status-change event."""
        if not self._kyc_url:
            logger.debug("KYC_WEBHOOK_URL not configured — skipping.")
            return

        payload = {
            "event":         "kyc.status_changed",
            "user_id":       user_id,
            "status":        status,
            "attempt_count": attempt_count,
            "timestamp":     int(time.time()),
            **(metadata or {}),
        }
        await self._send(self._kyc_url, payload)

    # Backward-compatible alias used by kyc_service.py
    async def notify_status_change(self, payload: Dict[str, Any]) -> None:
        if not self._kyc_url:
            logger.debug("KYC_WEBHOOK_URL not configured — skipping.")
            return
        await self._send(self._kyc_url, payload)

    # ── Credit scoring ────────────────────────────────────────────────────────

    async def notify_score_change(
        self,
        user_id:    int,
        old_score:  Optional[int],
        new_score:  int,
        risk_level: str,
        upload_id:  Optional[str] = None,
    ) -> None:
        """Fire a credit score-change event."""
        if not self._credit_url:
            logger.debug("CREDIT_WEBHOOK_URL not configured — skipping.")
            return

        payload = {
            "event":      "credit.score_changed",
            "user_id":    user_id,
            "old_score":  old_score,
            "new_score":  new_score,
            "risk_level": risk_level,
            "upload_id":  upload_id,
            "timestamp":  int(time.time()),
        }
        await self._send(self._credit_url, payload)


# Module-level singleton
webhook_service = WebhookService()
