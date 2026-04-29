"""
app/services/kyc_service.py — KYC pipeline orchestration (Asynchronous).
"""

import uuid
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from fastapi import UploadFile, HTTPException, status

from app.models.kyc import KYC, KYCStatus
from app.ai.ocr import extract_text_from_id
from app.ai.face_match import count_faces, check_liveness, match_faces
from app.ai.document_check import check_document_authenticity
from app.services.audit_service import AuditService
from app.services.storage_service import storage
from app.services.webhook_service import webhook_service
from app.utils.image_validation import validate_image_bytes
from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import pii_security

logger = get_logger(__name__)


def _save_image(
    image_bytes: bytes,
    user_id: int,
    label: str,
    original_filename: str,
) -> str:
    suffix   = Path(original_filename or "").suffix.lower() or ".jpg"
    filename = f"{user_id}_{label}_{uuid.uuid4().hex}{suffix}"
    return storage.save(image_bytes, filename)


# ---------------------------------------------------------------------------
# Decryption helper — returns a plain dict, never mutates the ORM object
# ---------------------------------------------------------------------------
def _build_decrypted_dict(record: KYC) -> dict:
    """
    Return a plain dict with PII fields decrypted.
    We never mutate the ORM-attached instance — that would dirty the session
    and risk writing decrypted data back to the DB on the next flush.
    """
    if record is None:
        return {}

    ocr_data = record.ocr_data
    if ocr_data:
        try:
            ocr_data = json.loads(pii_security.decrypt(ocr_data))
        except Exception:
            ocr_data = {"error": "decryption_failed"}

    return {
        "id":                  record.id,
        "user_id":             record.user_id,
        "status":              record.status,
        "is_active":           record.is_active,
        "id_type":             record.id_type,
        "id_number":           pii_security.decrypt(record.id_number),
        "nationality":         pii_security.decrypt(record.nationality),
        "country":             pii_security.decrypt(record.country),
        "full_name":           pii_security.decrypt(record.full_name),
        "dob":                 pii_security.decrypt(record.dob),
        "gender":              record.gender,
        "document_expires_at": record.document_expires_at,
        "ocr_data":            ocr_data,
        "face_match_score":    record.face_match_score,
        "liveness_score":      record.liveness_score,
        "authenticity_score":  record.authenticity_score,
        "attempt_count":       record.attempt_count,
        "id_image_url":        record.id_image_url,
        "selfie_image_url":    record.selfie_image_url,
        "expires_at":          record.expires_at,
        "reviewer_id":         record.reviewer_id,
        "reviewer_note":       record.reviewer_note,
        "reviewed_at":         record.reviewed_at,
        "created_at":          record.created_at,
        # updated_at: read directly — avoids lazy-load after commit
        "updated_at":          record.__dict__.get("updated_at"),
    }


class KYCService:
    def __init__(self, db: AsyncSession):
        self.db            = db
        self.audit_service = AuditService(db)

    # ── helpers ──────────────────────────────────────────────────────────────

    async def _get_record(self, user_id: int) -> KYC | None:
        result = await self.db.execute(
            select(KYC)
            .where(KYC.user_id == user_id, KYC.is_active == True)
            .order_by(KYC.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def _get_attempt_count(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(KYC).where(KYC.user_id == user_id)
        )
        return result.scalar() or 0

    async def _guard_resubmission(self, record: "KYC | None") -> None:
        if record is None:
            return
        if record.status == KYCStatus.VERIFIED:
            if record.expires_at and record.expires_at < datetime.now(timezone.utc):
                return
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="KYC already verified.",
            )
        attempt_count = await self._get_attempt_count(record.user_id)
        if attempt_count >= settings.KYC_MAX_RESUBMISSIONS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Max attempts ({settings.KYC_MAX_RESUBMISSIONS}) reached.",
            )

    # ── main pipeline ─────────────────────────────────────────────────────────

    async def process_kyc(
        self,
        user_id: int,
        id_card: UploadFile,
        selfie:  UploadFile,
        id_type: str = "national_id",
    ) -> dict:
        try:
            id_card_bytes = await id_card.read()
            selfie_bytes  = await selfie.read()

            validate_image_bytes(id_card_bytes, "id_card", id_card.content_type)
            validate_image_bytes(selfie_bytes,  "selfie",  selfie.content_type)

            existing = await self._get_record(user_id)
            await self._guard_resubmission(existing)

            # Archive previous active record
            if existing:
                await self.db.execute(
                    update(KYC)
                    .where(KYC.user_id == user_id, KYC.is_active == True)
                    .values(is_active=False, status=KYCStatus.RESUBMITTED)
                )
                await self.db.commit()

            # ── Save images ───────────────────────────────────────────────────
            id_image_url     = _save_image(id_card_bytes, user_id, "id",     id_card.filename or "id_card")
            selfie_image_url = _save_image(selfie_bytes,  user_id, "selfie", selfie.filename  or "selfie")

            # ── Face detection ────────────────────────────────────────────────
            selfie_faces = count_faces(selfie_bytes, "selfie")
            id_faces     = count_faces(id_card_bytes, "id_card")

            # -1 means the detector encountered an error (e.g. TF backend issue).
            # We treat this as "unknown" rather than blocking the whole pipeline.
            # A face count of 0 (confirmed absence) is still a hard rejection.
            if selfie_faces == 0:
                raise HTTPException(status_code=422, detail="No face detected in selfie.")
            if id_faces == 0:
                raise HTTPException(status_code=422, detail="No face detected on ID.")
            # If detection errored (-1), log a warning and continue
            if selfie_faces == -1 or id_faces == -1:
                logger.warning(
                    f"Face detection returned -1 (detector error): "
                    f"selfie={selfie_faces}, id={id_faces}. Continuing with face match."
                )

            # ── Liveness ──────────────────────────────────────────────────────
            liveness        = check_liveness(selfie_bytes)
            liveness_score  = liveness["score"]
            liveness_passed = liveness["passed"]

            # ── OCR + document check ──────────────────────────────────────────
            ocr_result         = extract_text_from_id(id_card_bytes, id_type=id_type)
            doc_check          = check_document_authenticity(id_card_bytes, ocr_result, id_type)
            authenticity_score = doc_check["score"]
            doc_passed         = doc_check["passed"]

            # ── Face matching ─────────────────────────────────────────────────
            match_score = match_faces(id_card_bytes, selfie_bytes)

            # ── Duplicate ID check (via blind index) ──────────────────────────
            id_num      = ocr_result.get("id_number")
            id_num_hash = pii_security.blind_index(id_num) if id_num else None

            if id_num_hash:
                dup = await self.db.execute(
                    select(KYC).where(
                        KYC.id_number_hash == id_num_hash,
                        KYC.status == KYCStatus.VERIFIED,
                        KYC.user_id != user_id,
                    )
                )
                if dup.scalar_one_or_none():
                    raise HTTPException(
                        status_code=409,
                        detail="ID already verified by another user.",
                    )

            # ── Determine verification status ─────────────────────────────────
            # doc_passed: hard failure only on resolution, expired doc, or MRZ forgery.
            # Missing OCR fields (id_number, name) are a soft signal — route to PENDING
            # for human review rather than outright rejection.
            face_verified  = match_score >= settings.KYC_FACE_MATCH_THRESHOLD
            face_pending   = match_score >= settings.KYC_FACE_MATCH_MANUAL_THRESHOLD
            live_verified  = liveness_passed or not settings.KYC_REQUIRE_LIVENESS
            live_pending   = (
                liveness_score >= settings.KYC_LIVENESS_MANUAL_THRESHOLD
                or not settings.KYC_REQUIRE_LIVENESS
            )
            # A document passes if it clears the hard structural checks.
            # OCR field presence (name / ID number) is a soft signal — it
            # degrades the score but does not block human-reviewed approvals.
            doc_hard_passed = (
                doc_check.get("checks", {}).get("resolution", True)
                and doc_check.get("checks", {}).get("not_expired", True)
                and not doc_check.get("checks", {}).get("mrz_checksum") == False
            )

            if face_verified and live_verified and doc_hard_passed and doc_passed:
                verification_status = KYCStatus.VERIFIED
            elif face_pending and live_pending and doc_hard_passed:
                # Route to PENDING even if OCR fields are missing — human reviewer
                # can inspect the image and approve / reject manually.
                verification_status = KYCStatus.PENDING
            else:
                verification_status = KYCStatus.REJECTED

            # ── Parse document expiry & DOB ──────────────────────────────────
            mrz        = ocr_result.get("mrz", {})
            doc_expiry = None
            expiry_raw = ocr_result.get("expiry_date")
            if expiry_raw:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y"):
                    try:
                        doc_expiry = datetime.strptime(expiry_raw, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            doc_dob = None
            dob_raw = ocr_result.get("dob")
            if dob_raw:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y"):
                    try:
                        doc_dob = datetime.strptime(dob_raw, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue

            # ── Persist KYC record ────────────────────────────────────────────
            kyc_record = KYC(
                user_id            = user_id,
                status             = verification_status,
                id_type            = id_type,
                id_number          = pii_security.encrypt(id_num),
                id_number_hash     = id_num_hash,
                nationality        = pii_security.encrypt(ocr_result.get("nationality")),
                country            = pii_security.encrypt(ocr_result.get("country")),
                full_name          = pii_security.encrypt(ocr_result.get("full_name")),
                dob                = pii_security.encrypt(doc_dob.isoformat() if doc_dob else None),
                gender             = ocr_result.get("gender"),
                document_expires_at= doc_expiry,
                ocr_data           = pii_security.encrypt(json.dumps(ocr_result)),
                face_match_score   = match_score,
                liveness_score     = liveness_score,
                authenticity_score = authenticity_score,
                id_image_url       = id_image_url,
                selfie_image_url   = selfie_image_url,
                attempt_count      = (await self._get_attempt_count(user_id)) + 1,
                is_active          = True,
            )

            if verification_status == KYCStatus.VERIFIED:
                kyc_record.expires_at = (
                    datetime.now(timezone.utc) + timedelta(days=settings.KYC_EXPIRY_DAYS)
                )

            self.db.add(kyc_record)
            await self.db.commit()
            await self.db.refresh(kyc_record)   # load all server-generated columns

            # ── GDPR: delete images on rejection ─────────────────────────────
            if verification_status == KYCStatus.REJECTED:
                storage.delete(id_image_url)
                storage.delete(selfie_image_url)
                # Update in-memory only — no second commit needed for image URLs
                # (they are already saved; we just null them in the response)
                kyc_record.id_image_url     = None
                kyc_record.selfie_image_url = None

            # ── Webhook + audit ───────────────────────────────────────────────
            await webhook_service.notify_status_change({
                "user_id":   user_id,
                "status":    verification_status.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            await self.audit_service.log_action(
                action   = "KYC_VERIFICATION",
                user_id  = user_id,
                status   = "SUCCESS" if verification_status == KYCStatus.VERIFIED else "REJECTED",
                metadata = {"face_match": match_score, "liveness": liveness_score},
            )

            # Return a plain dict — Pydantic reads it via from_attributes=True
            return _build_decrypted_dict(kyc_record)

        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            logger.error(f"KYC pipeline error: {exc}", exc_info=True)
            await self.audit_service.log_action(
                action   = "KYC_VERIFICATION",
                user_id  = user_id,
                status   = "ERROR",
                metadata = {"error": str(exc)},
            )
            raise HTTPException(
                status_code=500,
                detail="Internal KYC processing error.",
            )

    # ── Read methods ──────────────────────────────────────────────────────────

    async def get_kyc_status(self, user_id: int) -> dict | None:
        record = await self._get_record(user_id)
        if record is None:
            return None
        return _build_decrypted_dict(record)

    async def get_kyc_history(self, user_id: int) -> List[dict]:
        result = await self.db.execute(
            select(KYC).where(KYC.user_id == user_id).order_by(KYC.created_at.desc())
        )
        return [_build_decrypted_dict(r) for r in result.scalars().all()]

    async def admin_review(
        self,
        user_id:     int,
        reviewer_id: int,
        approved:    bool,
        note:        str = None,
    ) -> dict:
        record = await self._get_record(user_id)
        if not record:
            raise HTTPException(status_code=404, detail="KYC record not found.")

        record.status       = KYCStatus.VERIFIED if approved else KYCStatus.REJECTED
        record.reviewer_id  = reviewer_id
        record.reviewer_note= note
        record.reviewed_at  = datetime.now(timezone.utc)
        if approved:
            record.expires_at = record.reviewed_at + timedelta(days=settings.KYC_EXPIRY_DAYS)

        await self.db.commit()
        await self.db.refresh(record)
        return _build_decrypted_dict(record)

    async def list_kyc_records(
        self,
        status_filter:    KYCStatus = None,
        expired_only:     bool      = False,
        user_id:          int       = None,
        search_id_number: str       = None,
        page:             int       = 1,
        page_size:        int       = 20,
    ) -> dict:
        page_size = min(page_size, 100)
        stmt = select(KYC)

        if status_filter:
            stmt = stmt.where(KYC.status == status_filter)
        if expired_only:
            stmt = stmt.where(KYC.expires_at < datetime.now(timezone.utc))
        if user_id:
            stmt = stmt.where(KYC.user_id == user_id)
        if search_id_number:
            # Use blind index for exact-match search on encrypted column
            id_hash = pii_security.blind_index(search_id_number)
            stmt    = stmt.where(KYC.id_number_hash == id_hash)

        total_result = await self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        total = total_result.scalar() or 0

        rows_result = await self.db.execute(
            stmt.order_by(KYC.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = rows_result.scalars().all()

        return {
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "items":     [_build_decrypted_dict(i) for i in items],
        }
