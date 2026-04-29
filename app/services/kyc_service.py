"""
app/services/kyc_service.py — KYC pipeline orchestration (Asynchronous).

Full pipeline:
  1. Read + validate uploads (MIME, size, decodability)
  2. Guard: block if already VERIFIED; enforce max resubmission cap
  3. Persist images to local storage
  4. Face count pre-check (≥1 in selfie, ≥1 in ID)
  5. Liveness check on selfie
  6. OCR extraction (document-type-aware, multi-variant)
  7. Document authenticity heuristics
  8. Face matching (VGG-Face via DeepFace)
  9. Duplicate ID detection (blind index)
 10. Determine VERIFIED / PENDING / REJECTED using configurable thresholds
 11. Upsert KYC record
 12. GDPR: delete images on rejection
 13. Emit webhook + audit log
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


# ---------------------------------------------------------------------------
# Storage helper
# ---------------------------------------------------------------------------
def _save_image(image_bytes: bytes, user_id: int, label: str, original_filename: str) -> str:
    suffix   = Path(original_filename or "").suffix.lower() or ".jpg"
    filename = f"{user_id}_{label}_{uuid.uuid4().hex}{suffix}"
    return storage.save(image_bytes, filename)


# ---------------------------------------------------------------------------
# Decryption helper — returns a plain dict, never mutates the ORM object
# ---------------------------------------------------------------------------
def _build_decrypted_dict(record: KYC) -> dict:
    """
    Return a plain dict with PII fields decrypted.
    Never mutates the ORM-attached instance.
    """
    if record is None:
        return {}

    ocr_data = record.ocr_data
    if ocr_data:
        try:
            ocr_data = json.loads(pii_security.decrypt(ocr_data))
        except Exception:
            ocr_data = {"error": "decryption_failed"}

    # Decrypt dob string back to datetime if possible
    dob_value = None
    dob_raw = pii_security.decrypt(record.dob)
    if dob_raw:
        # Pydantic's datetime.fromisoformat can be picky with timezones.
        # We ensure it's treated as a date-time if it looks like one.
        try:
            # Handle "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS..."
            if "T" not in dob_raw and len(dob_raw) == 10:
                dob_value = datetime.strptime(dob_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                dob_value = datetime.fromisoformat(dob_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            dob_value = None

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
        "dob":                 dob_value,
        "gender":              record.gender,
        "document_expires_at": record.document_expires_at,
        "document_issued_at":  record.document_issued_at,
        "ocr_data":            ocr_data,
        "face_match_score":    record.face_match_score,
        "liveness_score":      record.liveness_score,
        "liveness_details":    record.liveness_details,
        "authenticity_score":  record.authenticity_score,
        "rejection_reason":    record.rejection_reason,
        "attempt_count":       record.attempt_count,
        "id_image_url":        record.id_image_url,
        "selfie_image_url":    record.selfie_image_url,
        "expires_at":          record.expires_at,
        "reviewer_id":         record.reviewer_id,
        "reviewer_note":       record.reviewer_note,
        "reviewed_at":         record.reviewed_at,
        "created_at":          record.created_at,
        "updated_at":          record.__dict__.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Rejection reason builder
# ---------------------------------------------------------------------------
def _build_rejection_reason(
    face_verified: bool,
    face_pending: bool,
    live_verified: bool,
    live_pending: bool,
    doc_hard_passed: bool,
    doc_passed: bool,
    liveness: dict,
    doc_check: dict,
    match_score: float,
) -> str:
    reasons = []
    if not doc_hard_passed:
        reasons.append(doc_check.get("reason") or "Document failed structural checks")
    if not face_pending:
        reasons.append(
            f"Face match score too low ({match_score:.2f}, "
            f"minimum {settings.KYC_FACE_MATCH_MANUAL_THRESHOLD:.2f} required)"
        )
    if not live_pending and settings.KYC_REQUIRE_LIVENESS:
        reasons.append(liveness.get("reason") or "Liveness check failed")
    if not reasons:
        reasons.append("Verification criteria not met")
    return "; ".join(reasons)


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
                return   # expired — re-verification permitted
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="KYC already verified. No resubmission needed.",
            )
        attempt_count = await self._get_attempt_count(record.user_id)
        if attempt_count >= settings.KYC_MAX_RESUBMISSIONS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Maximum verification attempts ({settings.KYC_MAX_RESUBMISSIONS}) reached.",
            )

    # ── main pipeline ─────────────────────────────────────────────────────────

    async def process_kyc(
        self,
        user_id:          int,
        id_card:          UploadFile,
        selfie:           UploadFile,
        id_type:          str = "national_id",
        # ── Manual override fields (user-entered, override OCR when provided) ──
        manual_full_name: Optional[str] = None,
        manual_id_number: Optional[str] = None,
        manual_issue_date: Optional[str] = None,   # ISO date string YYYY-MM-DD
        manual_expiry_date: Optional[str] = None,  # ISO date string YYYY-MM-DD
        manual_country:   Optional[str] = None,
        manual_nationality: Optional[str] = None,
    ) -> dict:
        try:
            # ── 1. Read & validate ────────────────────────────────────────────
            id_card_bytes = await id_card.read()
            selfie_bytes  = await selfie.read()

            validate_image_bytes(id_card_bytes, "id_card", id_card.content_type)
            validate_image_bytes(selfie_bytes,  "selfie",  selfie.content_type)

            # ── 2. Guard resubmission ─────────────────────────────────────────
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

            # ── 3. Save images ────────────────────────────────────────────────
            id_image_url     = _save_image(id_card_bytes, user_id, "id",     id_card.filename or "id_card")
            selfie_image_url = _save_image(selfie_bytes,  user_id, "selfie", selfie.filename  or "selfie")

            # ── 4. Face detection ─────────────────────────────────────────────
            selfie_faces = count_faces(selfie_bytes, "selfie")
            id_faces     = count_faces(id_card_bytes, "id_card")

            # 0 = confirmed no face; -1 = detector error
            if selfie_faces == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No face detected in selfie. Please upload a clear photo of your face.",
                )
            if id_faces == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No face detected on ID document. Please upload a clear photo of your ID.",
                )
            
            # Explicitly warn on detector errors but allow the pipeline to attempt face matching
            if selfie_faces == -1 or id_faces == -1:
                logger.warning(
                    f"Face detection encountered a system error (selfie={selfie_faces}, id={id_faces}). "
                    "Proceeding to face match as a fallback."
                )
            elif selfie_faces > 1:
                logger.warning(f"Multiple faces ({selfie_faces}) detected in selfie. Match accuracy may be affected.")

            # ── 5. Liveness check ─────────────────────────────────────────────
            liveness        = check_liveness(selfie_bytes)
            liveness_score  = liveness["score"]
            liveness_passed = liveness["passed"]
            liveness_details = {
                "sharpness_score":  liveness.get("sharpness_score"),
                "frequency_score":  liveness.get("frequency_score"),
                "reason":           liveness.get("reason"),
            }

            # ── 6. OCR + document check ───────────────────────────────────────
            ocr_result         = extract_text_from_id(id_card_bytes, id_type=id_type)

            # ── Apply manual overrides on top of OCR ──────────────────────────
            # Manual fields from the user always win over OCR extraction.
            # This handles the case where OCR fails or extracts wrong data.
            if manual_full_name:
                ocr_result["full_name"] = manual_full_name
            if manual_id_number:
                ocr_result["id_number"] = manual_id_number
            if manual_expiry_date:
                ocr_result["expiry_date"] = manual_expiry_date
            if manual_country:
                ocr_result["country"] = manual_country
            if manual_nationality:
                ocr_result["nationality"] = manual_nationality

            doc_check          = check_document_authenticity(id_card_bytes, ocr_result, id_type)
            authenticity_score = doc_check["score"]
            doc_passed         = doc_check["passed"]

            # ── 7. Document structural vs field checks ───────────────────────
            # doc_passed (full check): requires OCR fields like ID num, expiry to be extracted.
            # doc_hard_passed (structural): only requires basic authenticity (MRZ checksum, resolution).
            # This allows IDs with poor OCR but valid structure to be routed to PENDING.
            doc_hard_passed = (
                doc_check.get("checks", {}).get("resolution", True)
                and doc_check.get("checks", {}).get("not_expired", True)
                and doc_check.get("checks", {}).get("mrz_checksum", True) is not False
            )

            # ── 8. Face matching ──────────────────────────────────────────────
            match_score = match_faces(id_card_bytes, selfie_bytes)
            # match_faces always returns a float (0.0 on failure)

            # ── 8. Duplicate ID check ─────────────────────────────────────────
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
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This ID document is already verified under another account.",
                    )

            # ── 9. Determine verification status ──────────────────────────────
            face_verified = match_score >= settings.KYC_FACE_MATCH_THRESHOLD
            face_pending  = match_score >= settings.KYC_FACE_MATCH_MANUAL_THRESHOLD
            live_verified = liveness_passed or not settings.KYC_REQUIRE_LIVENESS
            live_pending  = (
                liveness_score >= settings.KYC_LIVENESS_MANUAL_THRESHOLD
                or not settings.KYC_REQUIRE_LIVENESS
            )

            if face_verified and live_verified and doc_hard_passed and doc_passed:
                verification_status = KYCStatus.VERIFIED
                rejection_reason    = None
            elif face_pending and live_pending and doc_hard_passed:
                # Route to PENDING for human review — OCR fields may be missing
                # but structural checks passed and face is plausible
                verification_status = KYCStatus.PENDING
                rejection_reason    = None
            else:
                verification_status = KYCStatus.REJECTED
                rejection_reason    = _build_rejection_reason(
                    face_verified, face_pending,
                    live_verified, live_pending,
                    doc_hard_passed, doc_passed,
                    liveness, doc_check, match_score,
                )

            # ── 10. Parse document dates ──────────────────────────────────────
            _DATE_FMTS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y")

            def _parse_date(raw: Optional[str]) -> Optional[datetime]:
                if not raw:
                    return None
                for fmt in _DATE_FMTS:
                    try:
                        return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                return None

            doc_expiry = _parse_date(ocr_result.get("expiry_date"))
            doc_dob    = _parse_date(ocr_result.get("dob"))

            # Issue date: manual override takes priority, then OCR
            issue_raw  = manual_issue_date or ocr_result.get("issue_date")
            doc_issued = _parse_date(issue_raw)

            # ── 11. Persist KYC record ────────────────────────────────────────
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
                document_issued_at = doc_issued,
                ocr_data           = pii_security.encrypt(json.dumps(ocr_result)),
                face_match_score   = match_score,
                liveness_score     = liveness_score,
                liveness_details   = liveness_details,
                authenticity_score = authenticity_score,
                rejection_reason   = rejection_reason,
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
            await self.db.refresh(kyc_record)

            # ── 12. GDPR: delete images on rejection ──────────────────────────
            if verification_status == KYCStatus.REJECTED:
                storage.delete(id_image_url)
                storage.delete(selfie_image_url)
                kyc_record.id_image_url     = None
                kyc_record.selfie_image_url = None

            # ── 13. Webhook + audit ───────────────────────────────────────────
            await webhook_service.notify_kyc_status_change(
                user_id       = user_id,
                status        = verification_status.value,
                attempt_count = kyc_record.attempt_count,
                metadata      = {
                    "face_match_score":   match_score,
                    "liveness_score":     liveness_score,
                    "authenticity_score": authenticity_score,
                    "rejection_reason":   rejection_reason,
                },
            )

            await self.audit_service.log_action(
                action   = "KYC_VERIFICATION",
                user_id  = user_id,
                status   = "SUCCESS" if verification_status == KYCStatus.VERIFIED else verification_status.value.upper(),
                metadata = {
                    "face_match":         match_score,
                    "liveness":           liveness_score,
                    "authenticity":       authenticity_score,
                    "verification_status": verification_status.value,
                    "rejection_reason":   rejection_reason,
                },
            )

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
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal KYC processing error. Please try again.",
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active KYC record found for this user.",
            )

        record.status        = KYCStatus.VERIFIED if approved else KYCStatus.REJECTED
        record.reviewer_id   = reviewer_id
        record.reviewer_note = note
        record.reviewed_at   = datetime.now(timezone.utc)
        if approved:
            record.expires_at        = record.reviewed_at + timedelta(days=settings.KYC_EXPIRY_DAYS)
            record.rejection_reason  = None
        else:
            record.rejection_reason  = f"Manually rejected by reviewer. Note: {note or 'No note provided.'}"

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
