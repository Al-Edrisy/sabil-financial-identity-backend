#!/bin/bash

# Group 1: Core Infrastructure & Config Updates
git add requirements.txt docker/Dockerfile docker/docker-compose.yml healthcheck.py .env.example .gitignore assumptions.md
git commit -m "chore: update core infrastructure, dependencies, and docker configuration"

# Group 2: Database Models & Migrations Setup
git add app/database/base.py app/database/session.py app/database/migrations/ app/models/user.py app/models/kyc.py app/models/wallet.py app/models/audit.py app/models/credit_score.py app/models/transaction.py app/models/parsed_transaction.py
git commit -m "feat: setup database models and alembic migrations configuration"

# Group 3: Authentication, Security, and Core Dependencies
git add app/core/security.py app/middleware/security_headers_middleware.py app/middleware/logging_middleware.py app/utils/encryption.py app/dependencies/auth.py app/dependencies/db.py app/dependencies/admin.py app/dependencies/rate_limit.py app/services/auth_service.py app/services/user_service.py app/services/audit_service.py
git commit -m "feat: enhance security, authentication, and core dependency injection"

# Group 4: KYC & Identity Verification AI Features
git add app/schemas/kyc.py app/schemas/user.py app/services/kyc_service.py app/ai/document_check.py app/ai/face_match.py app/ai/ocr_image.py app/utils/document_validation.py app/utils/image_validation.py app/services/storage_service.py app/api/v1/routes/kyc.py
git commit -m "feat: implement advanced KYC verification pipeline with OCR and face match"

# Group 5: Transactions, Wallets & Credit Scoring Services
git add app/schemas/wallet.py app/schemas/credit_score.py app/schemas/transaction_parsed.py app/services/wallet_service.py app/services/transaction_service.py app/services/scoring_service.py app/services/statement_service.py app/services/signal_service.py app/services/categorizer_service.py app/ai/parsing/ app/utils/currencies.json app/utils/fx.py app/api/v1/routes/wallet.py app/api/v1/routes/credit.py
git commit -m "feat: add wallet management, transaction processing, and credit scoring"

# Group 6: Admin Routes, API Adjustments & Webhooks
git add app/api/v1/router.py app/api/v1/routes/auth.py app/api/v1/routes/user.py app/api/v1/routes/admin_credit.py app/api/v1/routes/admin_kyc.py app/services/webhook_service.py app/api/v1/websockets/
git commit -m "feat: integrate admin routes, webhooks, and restructure API endpoints"

# Group 7: Tests, Scripts, and Main App Updates
git add app/tests/ generate_openapi.py enrich_openapi.py scratch_admin.py scripts/ Sabil_Postman_Collection.json scratch/ app/main.py
git commit -m "test: add test suites, openapi generation scripts, and update main entrypoint"

# Push the changes
git push origin main
