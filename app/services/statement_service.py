"""
app/services/statement_service.py — Orchestrates the full credit scoring
pipeline from document upload to score persistence.

Supports: JPEG, PNG, WebP (OCR), PDF (pdfplumber), CSV, TXT
Multiple files per session — all contribute to the same score.
"""

import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.parsed_transaction import (
    ParsedTransaction,
    ParsedTransactionType,
    ParsedTransactionSource,
)
from app.models.credit_score import CreditScore
from app.ai.parsing.statement_preprocessor import preprocess_statement
from app.ai.parsing.transaction_parser import parse_transactions
from app.ai.ocr import get_statement_ocr_reader
from app.services.categorizer_service import categorize_many
from app.services.signal_service import compute_signals
from app.services.scoring_service import (
    compute_score,
    get_risk_level,
    generate_insights,
    build_transactions_summary,
)
from app.services.audit_service import AuditService
from app.services.storage_service import get_storage
from app.services.webhook_service import webhook_service
from app.utils.document_validation import (
    validate_financial_document,
    get_file_category,
    extract_text_from_pdf,
    extract_text_from_csv,
    extract_text_from_plain,
)
from app.utils.fx import get_currency_for_country, convert_currency
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_TYPE_MAP = {
    "income":  ParsedTransactionType.INCOME,
    "expense": ParsedTransactionType.EXPENSE,
    "unknown": ParsedTransactionType.UNKNOWN,
}

class StatementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AuditService(db)
        self._storage = get_storage()

    async def upload_statements_batch(
        self,
        user_id:      int,
        files:        List[UploadFile],
        user_country: Optional[str] = None,
    ) -> dict:
        """
        Processes multiple financial documents, extracts transactions,
        and recomputes the user's credit score.
        """
        upload_id = str(uuid.uuid4())
        all_parsed_rows = []
        
        # ── 1. Process each file ─────────────────────────────────────────────
        for file in files:
            content = await file.read()
            # Basic validation (mime, size)
            validate_financial_document(content, file.filename, file.content_type)
            
            # Save to storage
            file_category = get_file_category(file.filename, file.content_type)
            suffix = Path(file.filename or "").suffix or ".bin"
            saved_path = self._storage.save(content, f"{user_id}/{upload_id}_{uuid.uuid4().hex}{suffix}")

            # Extract text based on type
            text_lines = []
            if file_category == "pdf":
                text_lines = extract_text_from_pdf(content)
            elif file_category == "csv":
                text_lines = extract_text_from_csv(content)
            elif file_category == "text":
                text_lines = extract_text_from_plain(content)
            elif file_category == "image":
                # OCR for images
                preprocessed = preprocess_statement(content)
                if preprocessed:
                    reader_latin, reader_arabic = get_statement_ocr_reader()
                    # Simple strategy: try both, pick best lines
                    # (Simplified for now — just using latin if available)
                    raw = reader_latin.readtext(preprocessed["processed"], detail=0) if reader_latin else []
                    text_lines = raw

            # ── 2. Parse transactions from text ──────────────────────────────
            parsed_rows = parse_transactions(text_lines)
            
            # Apply currency conversion if country provided
            home_currency = get_currency_for_country(user_country) if user_country else "USD"
            
            for row in parsed_rows:
                # Normalise amount to USD (signal service requirement)
                normalized_usd, _ = convert_currency(row.amount, row.currency or home_currency, "USD")
                
                all_parsed_rows.append({
                    "user_id":           user_id,
                    "upload_id":         upload_id,
                    "raw_line":          row.raw_line,
                    "description":       row.description,
                    "amount":            row.amount,
                    "currency":          row.currency or home_currency,
                    "normalized_amount": normalized_usd,
                    "type":              _TYPE_MAP.get(row.type, ParsedTransactionType.UNKNOWN),
                    "transaction_date":  row.transaction_date,
                    "confidence":        row.confidence,
                    "needs_review":      row.needs_review,
                })

        if not all_parsed_rows:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No transactions could be extracted from the provided files.",
            )

        # ── 3. Categorize transactions ───────────────────────────────────────
        descriptions = [r["description"] for r in all_parsed_rows]
        categories = categorize_many(descriptions)
        for row, (cat, _) in zip(all_parsed_rows, categories):
            row["category"] = cat

        # ── 4. Persist transactions ──────────────────────────────────────────
        db_rows = [ParsedTransaction(**r) for r in all_parsed_rows]
        self.db.add_all(db_rows)
        await self.db.flush() # flush to get IDs if needed

        # ── 5. Recompute Credit Score ────────────────────────────────────────
        history_result = await self.db.execute(
            select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
        )
        all_tx_history = history_result.scalars().all()
        
        # Convert to dicts for signal service
        history_dicts = [
            {
                "normalized_usd":   t.normalized_amount,
                "type":             t.type,
                "transaction_date": t.transaction_date,
                "created_at":       t.created_at,
                "category":         t.category,
            }
            for t in all_tx_history
        ]

        signals = compute_signals(history_dicts)
        score_val = compute_score(signals)
        risk = get_risk_level(score_val)
        insights = generate_insights(signals, score_val)
        summary = build_transactions_summary(history_dicts)

        # Archive old scores
        await self.db.execute(
            update(CreditScore)
            .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
            .values(is_active=False)
        )

        # Create new score
        new_score = CreditScore(
            user_id              = user_id,
            score                = score_val,
            risk_level           = risk,
            income_level         = signals.income_level,
            income_stability     = signals.income_stability,
            savings_rate         = signals.savings_rate,
            activity             = signals.activity,
            burden               = signals.burden,
            insights             = insights,
            transactions_summary = summary,
            upload_id            = upload_id,
            transaction_count    = len(all_tx_history),
            data_quality         = signals.data_quality,
            is_active            = True,
        )
        self.db.add(new_score)
        
        await self.db.commit()
        await self.db.refresh(new_score)

        # ── 6. Finalize ──────────────────────────────────────────────────────
        await self.audit_service.log_action(
            action   = "CREDIT_SCORE_COMPUTATION",
            user_id  = user_id,
            metadata = {"upload_id": upload_id, "score": score_val, "risk": risk},
        )
        
        await webhook_service.notify_credit_score_update(
            user_id   = user_id,
            score     = score_val,
            risk_level= risk,
        )

        return {
            "upload_id":          upload_id,
            "row_count":          len(all_parsed_rows),
            "needs_review_count": sum(1 for r in all_parsed_rows if r["needs_review"]),
            "score":              new_score,
        }

    async def get_score(self, user_id: int) -> Optional[CreditScore]:
        result = await self.db.execute(
            select(CreditScore)
            .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
            .order_by(CreditScore.computed_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_review_queue(self, user_id: int) -> List[ParsedTransaction]:
        result = await self.db.execute(
            select(ParsedTransaction)
            .where(ParsedTransaction.user_id == user_id, ParsedTransaction.needs_review == True)
            .order_by(ParsedTransaction.transaction_date.desc())
        )
        return list(result.scalars().all())

    async def get_transactions(
        self,
        user_id:      int,
        page:         int = 1,
        page_size:    int = 20,
        tx_type:      Optional[str] = None,
        needs_review: Optional[bool] = None,
    ) -> dict:
        stmt = select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
        
        if tx_type:
            stmt = stmt.where(ParsedTransaction.type == ParsedTransactionType(tx_type))
        if needs_review is not None:
            stmt = stmt.where(ParsedTransaction.needs_review == needs_review)
            
        # Count
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0
        
        # Rows
        result = await self.db.execute(
            stmt.order_by(ParsedTransaction.transaction_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = result.scalars().all()
        
        return {
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "items":     items,
        }

    async def correct_transaction(
        self,
        tx_id:      int,
        user_id:    int,
        correction: dict,
    ) -> CreditScore:
        """
        Update a transaction manually and trigger a score recompute.
        """
        # Fetch transaction
        result = await self.db.execute(
            select(ParsedTransaction).where(ParsedTransaction.id == tx_id, ParsedTransaction.user_id == user_id)
        )
        tx = result.scalar_one_or_none()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Update fields
        for key, value in correction.items():
            if key == "type":
                setattr(tx, key, ParsedTransactionType(value))
            else:
                setattr(tx, key, value)
        
        # Mark as manual source and no longer needs review
        tx.source = ParsedTransactionSource.MANUAL
        tx.needs_review = False
        
        # If amount or currency changed, re-normalise
        if "amount" in correction or "currency" in correction:
            norm_usd, _ = convert_currency(tx.amount, tx.currency, "USD")
            tx.normalized_amount = norm_usd

        await self.db.flush()

        # Recompute score
        history_result = await self.db.execute(
            select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
        )
        all_tx_history = history_result.scalars().all()
        history_dicts = [
            {
                "normalized_usd":   t.normalized_amount,
                "type":             t.type,
                "transaction_date": t.transaction_date,
                "created_at":       t.created_at,
                "category":         t.category,
            }
            for t in all_tx_history
        ]

        signals = compute_signals(history_dicts)
        score_val = compute_score(signals)
        risk = get_risk_level(score_val)
        insights = generate_insights(signals, score_val)
        summary = build_transactions_summary(history_dicts)

        # Archive old scores
        await self.db.execute(
            update(CreditScore)
            .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
            .values(is_active=False)
        )

        new_score = CreditScore(
            user_id              = user_id,
            score                = score_val,
            risk_level           = risk,
            income_level         = signals.income_level,
            income_stability     = signals.income_stability,
            savings_rate         = signals.savings_rate,
            activity             = signals.activity,
            burden               = signals.burden,
            insights             = insights,
            transactions_summary = summary,
            upload_id            = tx.upload_id,
            transaction_count    = len(all_tx_history),
            data_quality         = signals.data_quality,
            is_active            = True,
        )
        self.db.add(new_score)
        await self.db.commit()
        await self.db.refresh(new_score)

        return new_score


class StatementService:
    def __init__(self, db: AsyncSession):
        self.db            = db
        self.audit_service = AuditService(db)
        self._storage      = get_storage("credit")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _extract_lines_from_file(
        self,
        file_bytes:   bytes,
        content_type: str,
        filename:     str,
    ) -> list:
        """Extract text lines from any supported file type."""
        category = get_file_category(content_type)
        if category == "image":
            return await self._ocr_image(file_bytes)
        elif category == "pdf":
            lines = extract_text_from_pdf(file_bytes)
            if not lines:
                logger.info(f"PDF has no text layer, attempting OCR: {filename}")
                lines = await self._ocr_image(file_bytes)
            return lines
        elif category == "csv":
            return extract_text_from_csv(file_bytes)
        elif category == "text":
            return extract_text_from_plain(file_bytes)
        return []

    async def _ocr_image(self, image_bytes: bytes) -> list:
        """
        Run OCR on a statement image using multi-variant preprocessing.
        Tries EasyOCR first (best quality), falls back to Tesseract if unavailable.
        """
        import cv2
        import numpy as np

        # ── Try EasyOCR first ─────────────────────────────────────────────────
        reader_latin, reader_arabic = get_statement_ocr_reader()
        if reader_latin is not None or reader_arabic is not None:
            return await self._ocr_image_easyocr(image_bytes, reader_latin, reader_arabic)

        # ── Fallback: Tesseract ───────────────────────────────────────────────
        return self._ocr_image_tesseract(image_bytes)

    async def _ocr_image_easyocr(self, image_bytes: bytes, reader_latin, reader_arabic) -> list:
        """EasyOCR path — multi-variant, multi-reader."""
        import cv2
        import numpy as np

        min_conf = settings.KYC_OCR_MIN_CONFIDENCE
        variants = []

        # Variant 0: standard statement preprocessing
        preprocessed = preprocess_statement(image_bytes)
        if preprocessed is not None:
            variants.append(("stmt_standard", preprocessed["processed"]))

        # Additional variants from raw image
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                if w < 1500:
                    scale = 1500 / w
                    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                variants.append(("raw_gray",   gray))
                variants.append(("clahe_only", clahe.apply(gray)))
                variants.append(("colour",     img))
        except Exception as e:
            logger.debug(f"OCR variant build error: {e}")

        if not variants:
            logger.error("No OCR variants could be built")
            return []

        best_lines = []
        best_score = -1.0

        readers = []
        if reader_latin  is not None:
            readers.append(("latin(en+tr)",  reader_latin))
        if reader_arabic is not None:
            readers.append(("arabic(en+ar)", reader_arabic))

        for reader_name, reader in readers:
            for variant_name, variant_img in variants:
                try:
                    ocr_results = reader.readtext(variant_img, detail=1, paragraph=False)
                    score = sum(
                        r[2] * len(r[1])
                        for r in ocr_results
                        if r[2] >= min_conf and r[1].strip()
                    )
                    lines = [r[1] for r in ocr_results if r[2] >= min_conf and r[1].strip()]
                    logger.debug(
                        f"OCR [{reader_name}][{variant_name}]: "
                        f"tokens={len(lines)} score={score:.1f}"
                    )
                    if score > best_score:
                        best_score = score
                        best_lines = lines
                except Exception as e:
                    logger.warning(f"OCR [{reader_name}][{variant_name}] failed: {e}")

        logger.info(f"EasyOCR best result: {len(best_lines)} lines, score={best_score:.1f}")
        return best_lines

    def _ocr_image_tesseract(self, image_bytes: bytes) -> list:
        """
        Tesseract fallback OCR — used when EasyOCR is not installed.
        Supports English, Turkish, and Arabic (if language packs installed).
        """
        try:
            import pytesseract
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(image_bytes))

            # Try multilingual first, fall back to English only
            for lang in ["eng+tur+ara", "eng+tur", "eng"]:
                try:
                    text = pytesseract.image_to_string(img, lang=lang)
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if lines:
                        logger.info(f"Tesseract OCR ({lang}): {len(lines)} lines extracted")
                        return lines
                except Exception:
                    continue

            logger.warning("Tesseract: all language configs failed")
            return []

        except ImportError:
            logger.error("Neither EasyOCR nor pytesseract is installed. Cannot perform OCR.")
            return []
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return []

    def _normalize_to_user_currency(self, rows: list, user_country: Optional[str]) -> list:
        """Convert all transaction amounts to the user's home currency."""
        if not user_country:
            return rows
        home_currency = get_currency_for_country(user_country)
        if home_currency == "USD":
            return rows
        for row in rows:
            if row.currency != home_currency:
                converted, rate = convert_currency(row.amount, row.currency, home_currency)
                row.normalized_usd = converted
                logger.debug(
                    f"FX: {row.amount} {row.currency} -> {converted} {home_currency} (rate={rate})"
                )
        return rows

    def _build_signal_input(self, rows: list) -> list:
        """Convert ORM rows to signal_service input dicts."""
        return [
            {
                "normalized_usd":   r.normalized_amount,
                "type":             r.type.value.lower() if hasattr(r.type, "value") else str(r.type).lower(),
                "transaction_date": r.transaction_date,
                "created_at":       r.created_at,
                "category":         r.category or "other",
            }
            for r in rows
        ]

    async def _compute_and_save_score(
        self,
        user_id:   int,
        upload_id: Optional[str] = None,
    ) -> CreditScore:
        """Recompute credit score from all user transactions and persist."""
        all_rows_result = await self.db.execute(
            select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
        )
        all_rows     = all_rows_result.scalars().all()
        signal_input = self._build_signal_input(all_rows)

        signals    = compute_signals(signal_input)
        score      = compute_score(signals)
        risk_level = get_risk_level(score)
        insights   = generate_insights(signals, score)
        tx_summary = build_transactions_summary(signal_input)

        await self.db.execute(
            update(CreditScore)
            .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
            .values(is_active=False)
        )

        record = CreditScore(
            user_id              = user_id,
            score                = score,
            risk_level           = risk_level,
            income_level         = signals.income_level,
            income_stability     = signals.income_stability,
            savings_rate         = signals.savings_rate,
            activity             = signals.activity,
            burden               = signals.burden,
            insights             = insights,
            transactions_summary = tx_summary,
            upload_id            = upload_id,
            transaction_count    = signals.transaction_count,
            data_quality         = signals.data_quality,
            is_active            = True,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    # ── Public methods ────────────────────────────────────────────────────────

    async def upload_statement(
        self,
        user_id:      int,
        image_file:   UploadFile,
        user_country: Optional[str] = None,
    ) -> dict:
        """Single-file upload. Delegates to upload_statements_batch."""
        return await self.upload_statements_batch(
            user_id      = user_id,
            files        = [image_file],
            user_country = user_country,
        )

    async def upload_statements_batch(
        self,
        user_id:      int,
        files:        List[UploadFile],
        user_country: Optional[str] = None,
    ) -> dict:
        """
        Process one or more financial documents (images, PDFs, CSVs).
        All files contribute to the same upload session and score computation.
        """
        if not files:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No files provided.",
            )

        upload_id    = uuid.uuid4().hex
        all_db_rows  = []
        file_results = []

        for file in files:
            file_bytes   = await file.read()
            content_type = file.content_type or ""
            filename     = file.filename or "document"

            try:
                category = validate_financial_document(file_bytes, filename, content_type)
            except HTTPException as e:
                file_results.append({"filename": filename, "status": "error", "error": e.detail, "rows": 0})
                logger.warning(f"Skipping invalid file '{filename}': {e.detail}")
                continue

            suffix   = Path(filename).suffix.lower() or f".{category}"
            savename = f"{user_id}_stmt_{upload_id}_{uuid.uuid4().hex[:8]}{suffix}"
            try:
                self._storage.save(file_bytes, savename)
            except Exception as e:
                logger.warning(f"Could not save file '{filename}': {e}")

            raw_lines = await self._extract_lines_from_file(file_bytes, content_type, filename)
            logger.info(f"File '{filename}': extracted {len(raw_lines)} lines (category={category})")
            for i, line in enumerate(raw_lines[:20]):
                logger.debug(f"  line[{i}]: {line!r}")

            if not raw_lines:
                file_results.append({"filename": filename, "status": "no_text", "error": "No text could be extracted.", "rows": 0})
                continue

            parsed_rows = parse_transactions(raw_lines)
            logger.info(f"File '{filename}': parsed {len(parsed_rows)} transactions")
            for i, row in enumerate(parsed_rows[:10]):
                logger.info(
                    f"  tx[{i}]: type={row.type} amount={row.amount} {row.currency} "
                    f"desc={row.description!r} date={row.transaction_date} conf={row.confidence:.2f}"
                )

            if not parsed_rows:
                file_results.append({"filename": filename, "status": "no_transactions", "error": "No transactions identified.", "rows": 0})
                continue

            parsed_rows = self._normalize_to_user_currency(parsed_rows, user_country)
            descriptions = [r.description for r in parsed_rows]
            categories   = categorize_many(descriptions)

            for row, (category_name, _cat_score) in zip(parsed_rows, categories):
                db_row = ParsedTransaction(
                    user_id          = user_id,
                    upload_id        = upload_id,
                    raw_line         = row.raw_line,
                    description      = row.description,
                    amount           = row.amount,
                    currency         = row.currency,
                    normalized_amount= row.normalized_usd,
                    type             = _TYPE_MAP.get(row.type, ParsedTransactionType.UNKNOWN),
                    category         = category_name,
                    transaction_date = row.transaction_date,
                    confidence       = row.confidence,
                    needs_review     = row.needs_review,
                    source           = ParsedTransactionSource.OCR_UPLOAD,
                )
                all_db_rows.append(db_row)

            file_results.append({"filename": filename, "status": "ok", "rows": len(parsed_rows), "category": category})

        if not all_db_rows:
            errors = [r["error"] for r in file_results if r.get("error")]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "No transactions could be extracted from any of the uploaded files. "
                    + ("Errors: " + "; ".join(errors) if errors else "")
                ),
            )

        self.db.add_all(all_db_rows)
        await self.db.flush()

        credit_score_record = await self._compute_and_save_score(user_id, upload_id)

        await self.audit_service.log_action(
            action   = "CREDIT_SCORE_COMPUTED",
            user_id  = user_id,
            status   = "SUCCESS",
            metadata = {
                "upload_id":    upload_id,
                "score":        credit_score_record.score,
                "risk_level":   credit_score_record.risk_level,
                "row_count":    len(all_db_rows),
                "file_count":   len(files),
                "data_quality": credit_score_record.data_quality,
                "file_results": file_results,
            },
        )
        await webhook_service.notify_score_change(
            user_id    = user_id,
            old_score  = None,
            new_score  = credit_score_record.score,
            risk_level = credit_score_record.risk_level,
            upload_id  = upload_id,
        )

        needs_review_count = sum(1 for r in all_db_rows if r.needs_review)
        return {
            "upload_id":          upload_id,
            "row_count":          len(all_db_rows),
            "needs_review_count": needs_review_count,
            "file_results":       file_results,
            "score":              credit_score_record,
        }

    async def get_score(self, user_id: int) -> Optional[CreditScore]:
        """Fetch the latest active CreditScore for a user."""
        result = await self.db.execute(
            select(CreditScore)
            .where(CreditScore.user_id == user_id, CreditScore.is_active == True)
            .order_by(CreditScore.computed_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_transactions(
        self,
        user_id:      int,
        page:         int  = 1,
        page_size:    int  = 20,
        tx_type:      Optional[str]  = None,
        needs_review: Optional[bool] = None,
    ) -> dict:
        """Paginated list of ParsedTransaction rows for a user."""
        from sqlalchemy import func as sqlfunc

        stmt = select(ParsedTransaction).where(ParsedTransaction.user_id == user_id)
        if tx_type and tx_type.lower() in _TYPE_MAP:
            stmt = stmt.where(ParsedTransaction.type == _TYPE_MAP[tx_type.lower()])
        if needs_review is not None:
            stmt = stmt.where(ParsedTransaction.needs_review == needs_review)

        count_result = await self.db.execute(
            select(sqlfunc.count()).select_from(stmt.subquery())
        )
        total = count_result.scalar() or 0

        rows_result = await self.db.execute(
            stmt.order_by(ParsedTransaction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = rows_result.scalars().all()
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    async def get_review_queue(self, user_id: int) -> list:
        """Return all transactions flagged needs_review=True for a user."""
        result = await self.db.execute(
            select(ParsedTransaction).where(
                ParsedTransaction.user_id == user_id,
                ParsedTransaction.needs_review == True,
            )
        )
        return result.scalars().all()

    async def correct_transaction(
        self,
        tx_id:      int,
        user_id:    int,
        correction: dict,
    ) -> CreditScore:
        """Apply a user correction to a ParsedTransaction, then recompute score."""
        result = await self.db.execute(
            select(ParsedTransaction).where(
                ParsedTransaction.id == tx_id,
                ParsedTransaction.user_id == user_id,
            )
        )
        tx = result.scalar_one_or_none()
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found.",
            )

        if "description"      in correction and correction["description"]:
            tx.description = correction["description"]
        if "amount"           in correction and correction["amount"]:
            tx.amount = correction["amount"]
        if "currency"         in correction and correction["currency"]:
            tx.currency = correction["currency"]
        if "type"             in correction and correction["type"]:
            tx.type = _TYPE_MAP.get(correction["type"], tx.type)
        if "category"         in correction and correction["category"]:
            tx.category = correction["category"]
        if "transaction_date" in correction and correction["transaction_date"]:
            tx.transaction_date = correction["transaction_date"]

        tx.needs_review = False
        tx.source       = ParsedTransactionSource.MANUAL
        await self.db.flush()

        return await self._compute_and_save_score(user_id)
