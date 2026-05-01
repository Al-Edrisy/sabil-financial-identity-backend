-- ═══════════════════════════════════════════════════════════════════════════
--  SABIL FINANCIAL IDENTITY — EGYPT DATABASE (sabil_eg)
--  User: Mohammed Ismail
--  Currency: EGP (Egyptian Pound) — note: 1 USD ≈ 48 EGP (2026 est.)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── SCHEMA ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    full_name        VARCHAR(120) NOT NULL,
    phone_number     VARCHAR(20)  UNIQUE NOT NULL,
    email            VARCHAR(150) UNIQUE,
    national_id      VARCHAR(50)  NOT NULL,
    nationality      VARCHAR(50)  DEFAULT 'Egyptian',
    country_code     CHAR(2)      DEFAULT 'EG',
    date_of_birth    DATE,
    gender           CHAR(1),
    is_active        BOOLEAN      DEFAULT TRUE,
    kyc_verified     BOOLEAN      DEFAULT FALSE,
    kyc_verified_at  TIMESTAMPTZ,
    onboarding_step  SMALLINT     DEFAULT 3,
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallets (
    id          SERIAL PRIMARY KEY,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    balance     NUMERIC(14,2) DEFAULT 0.00,
    currency    CHAR(3)       DEFAULT 'EGP',
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id               SERIAL PRIMARY KEY,
    user_id          INT REFERENCES users(id) ON DELETE CASCADE,
    transaction_date DATE          NOT NULL,
    description      VARCHAR(255)  NOT NULL,
    amount           NUMERIC(14,2) NOT NULL,
    currency         CHAR(3)       DEFAULT 'EGP',
    type             VARCHAR(20)   NOT NULL CHECK (type IN ('income','expense','transfer','saving')),
    category         VARCHAR(50),
    source           VARCHAR(30)   DEFAULT 'bank_statement',
    confidence       NUMERIC(4,3)  DEFAULT 1.000,
    created_at       TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receipts (
    id                SERIAL PRIMARY KEY,
    user_id           INT REFERENCES users(id) ON DELETE CASCADE,
    transaction_id    INT REFERENCES transactions(id) ON DELETE SET NULL,
    receipt_date      DATE          NOT NULL,
    merchant_name     VARCHAR(120),
    merchant_category VARCHAR(60),
    total_amount      NUMERIC(14,2) NOT NULL,
    currency          CHAR(3)       DEFAULT 'EGP',
    payment_method    VARCHAR(30)   DEFAULT 'cash',
    receipt_ref       VARCHAR(60),
    items             JSONB,
    notes             TEXT,
    created_at        TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sabil_scores (
    id                      SERIAL PRIMARY KEY,
    user_id                 INT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    score                   SMALLINT      NOT NULL CHECK (score BETWEEN 0 AND 1000),
    risk_level              VARCHAR(20)   NOT NULL,
    factor_income_regularity    NUMERIC(5,2),
    factor_income_expense_ratio NUMERIC(5,2),
    factor_savings_rate         NUMERIC(5,2),
    factor_activity_density     NUMERIC(5,2),
    factor_income_diversity     NUMERIC(5,2),
    factor_payment_commitment   NUMERIC(5,2),
    transaction_count       INT,
    active_months           INT,
    avg_monthly_income      NUMERIC(14,2),
    avg_monthly_expense     NUMERIC(14,2),
    income_sources          INT,
    data_quality            VARCHAR(20)   DEFAULT 'good',
    is_active               BOOLEAN       DEFAULT TRUE,
    computed_at             TIMESTAMPTZ   DEFAULT NOW(),
    updated_at              TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX idx_receipts_user_date     ON receipts(user_id, receipt_date DESC);

-- ═══════════════════════════════════════════════════════════════════════════
--  SEED DATA — MOHAMMED ISMAIL
--  Profile: Small business owner (electronics shop in Cairo),
--           consistent income from shop + online sales + rental income
--           Uses Instapay / Fawry / CIB bank transfers
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO users (full_name, phone_number, email, national_id, nationality, country_code,
                   date_of_birth, gender, is_active, kyc_verified, kyc_verified_at, onboarding_step)
VALUES ('Mohammed Ismail', '+201012345678', 'mohammed.ismail@eg.sabil.app',
        'EG-199001-29-00453', 'Egyptian', 'EG', '1990-01-20', 'M',
        TRUE, TRUE, NOW() - INTERVAL '20 days', 3);

INSERT INTO wallets (user_id, balance, currency)
VALUES (1, 42500.00, 'EGP');

-- Mohammed's 6 months of transactions (Dec 2025 - May 2026)
-- Shop income ~22,000 EGP/month + online ~4,500 + rent 7,000
-- Expenses: shop rent 12k + home rent 8k + stock ~8k + living ~5k
INSERT INTO transactions (user_id, transaction_date, description, amount, currency, type, category) VALUES
-- December 2025 (baseline)
(1, '2025-12-01', 'Electronics Shop Sales - December Week 1',  18500.00, 'EGP', 'income',   'business'),
(1, '2025-12-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2025-12-05', 'Stock Purchase - Samsung Accessories',       -8200.00, 'EGP', 'expense',  'business'),
(1, '2025-12-08', 'Home Rent - Nasr City Apartment',           -8000.00, 'EGP', 'expense',  'rent'),
(1, '2025-12-10', 'Jumia Online Store Sales',                   4200.00, 'EGP', 'income',   'online_sales'),
(1, '2025-12-12', 'Electricity Bill - Shop',                    -1800.00, 'EGP', 'expense',  'utilities'),
(1, '2025-12-14', 'Electronics Shop Sales - December Week 2',  14200.00, 'EGP', 'income',   'business'),
(1, '2025-12-16', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental'),
(1, '2025-12-18', 'Groceries - Carrefour',                      -3200.00, 'EGP', 'expense',  'groceries'),
(1, '2025-12-20', 'Employee Salaries x2',                       -9600.00, 'EGP', 'expense',  'salaries'),
(1, '2025-12-22', 'Electronics Shop Sales - Week 3',            9800.00, 'EGP', 'income',   'business'),
(1, '2025-12-25', 'Instapay Transfer - Savings',               -5000.00, 'EGP', 'saving',   'savings'),
(1, '2025-12-28', 'Fawry - Insurance Premium',                  -2100.00, 'EGP', 'expense',  'insurance'),
-- January 2026
(1, '2026-01-01', 'Electronics Shop Sales - January Week 1',   16800.00, 'EGP', 'income',   'business'),
(1, '2026-01-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2026-01-05', 'Stock Purchase - Cables & Chargers',         -7500.00, 'EGP', 'expense',  'business'),
(1, '2026-01-07', 'Home Rent - Nasr City Apartment',           -8000.00, 'EGP', 'expense',  'rent'),
(1, '2026-01-09', 'Jumia Online Store Sales',                   3800.00, 'EGP', 'income',   'online_sales'),
(1, '2026-01-12', 'Electronics Shop Sales - Week 2',           11200.00, 'EGP', 'income',   'business'),
(1, '2026-01-14', 'Electricity Bill - Shop & Home',             -2400.00, 'EGP', 'expense',  'utilities'),
(1, '2026-01-16', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental'),
(1, '2026-01-18', 'Groceries - Metro Market',                   -2800.00, 'EGP', 'expense',  'groceries'),
(1, '2026-01-20', 'Employee Salaries x2',                       -9600.00, 'EGP', 'expense',  'salaries'),
(1, '2026-01-22', 'Electronics Shop - Bulk Corporate Order',   22000.00, 'EGP', 'income',   'business'),
(1, '2026-01-25', 'Instapay Transfer - Savings',               -6000.00, 'EGP', 'saving',   'savings'),
(1, '2026-01-28', 'Internet + Mobile Business Lines',           -1400.00, 'EGP', 'expense',  'telecom'),
-- February 2026
(1, '2026-02-01', 'Electronics Shop Sales - Feb Week 1',       15600.00, 'EGP', 'income',   'business'),
(1, '2026-02-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2026-02-05', 'Stock Purchase - iPhone Accessories',        -9100.00, 'EGP', 'expense',  'business'),
(1, '2026-02-07', 'Home Rent - Nasr City Apartment',           -8000.00, 'EGP', 'expense',  'rent'),
(1, '2026-02-09', 'Jumia Sales',                                5100.00, 'EGP', 'income',   'online_sales'),
(1, '2026-02-12', 'Electronics Shop - Week 2',                 12400.00, 'EGP', 'income',   'business'),
(1, '2026-02-14', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental'),
(1, '2026-02-16', 'Utilities - Electricity & Water',            -2100.00, 'EGP', 'expense',  'utilities'),
(1, '2026-02-18', 'Groceries',                                  -3100.00, 'EGP', 'expense',  'groceries'),
(1, '2026-02-20', 'Employee Salaries x2',                       -9600.00, 'EGP', 'expense',  'salaries'),
(1, '2026-02-22', 'Electronics Shop - Week 3',                  9600.00, 'EGP', 'income',   'business'),
(1, '2026-02-25', 'Instapay Transfer - Savings',               -5500.00, 'EGP', 'saving',   'savings'),
(1, '2026-02-27', 'Restaurant - Team Lunch',                    -1200.00, 'EGP', 'expense',  'food'),
-- March 2026
(1, '2026-03-01', 'Electronics Shop Sales - March Week 1',     17200.00, 'EGP', 'income',   'business'),
(1, '2026-03-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2026-03-05', 'Stock Purchase - Ramadan Specials',         -10500.00, 'EGP', 'expense',  'business'),
(1, '2026-03-07', 'Home Rent - Nasr City',                     -8000.00, 'EGP', 'expense',  'rent'),
(1, '2026-03-09', 'Jumia + Noon Sales',                         6200.00, 'EGP', 'income',   'online_sales'),
(1, '2026-03-12', 'Electronics Shop - Week 2 (Ramadan Rush)',  24500.00, 'EGP', 'income',   'business'),
(1, '2026-03-14', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental'),
(1, '2026-03-16', 'Utilities',                                  -2200.00, 'EGP', 'expense',  'utilities'),
(1, '2026-03-18', 'Groceries - Ramadan Shopping',               -4500.00, 'EGP', 'expense',  'groceries'),
(1, '2026-03-20', 'Employee Salaries x2',                       -9600.00, 'EGP', 'expense',  'salaries'),
(1, '2026-03-22', 'Electronics Shop - Ramadan Week 3',         19800.00, 'EGP', 'income',   'business'),
(1, '2026-03-25', 'Instapay Transfer - Savings (Ramadan Bump)',  -8000.00, 'EGP', 'saving',   'savings'),
(1, '2026-03-28', 'Zakat / Charity Distribution',               -3000.00, 'EGP', 'expense',  'charity'),
-- April 2026
(1, '2026-04-01', 'Electronics Shop - Eid Season',             21000.00, 'EGP', 'income',   'business'),
(1, '2026-04-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2026-04-05', 'Stock Replenishment Post-Eid',               -7800.00, 'EGP', 'expense',  'business'),
(1, '2026-04-07', 'Home Rent - Nasr City',                     -8000.00, 'EGP', 'expense',  'rent'),
(1, '2026-04-09', 'Jumia Sales',                                4600.00, 'EGP', 'income',   'online_sales'),
(1, '2026-04-12', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental'),
(1, '2026-04-14', 'Utilities',                                  -2300.00, 'EGP', 'expense',  'utilities'),
(1, '2026-04-16', 'Groceries',                                  -2900.00, 'EGP', 'expense',  'groceries'),
(1, '2026-04-18', 'Employee Salaries x2',                       -9600.00, 'EGP', 'expense',  'salaries'),
(1, '2026-04-20', 'Electronics Shop - April Week 3',           13500.00, 'EGP', 'income',   'business'),
(1, '2026-04-25', 'Instapay Transfer - Savings',               -6000.00, 'EGP', 'saving',   'savings'),
(1, '2026-04-28', 'Insurance & Accountant Fee',                 -2800.00, 'EGP', 'expense',  'insurance'),
-- May 2026 (current)
(1, '2026-05-01', 'Electronics Shop - May Week 1',             15800.00, 'EGP', 'income',   'business'),
(1, '2026-05-03', 'Shop Rent - Ataba Market',                  -12000.00, 'EGP', 'expense',  'rent'),
(1, '2026-05-05', 'Stock Purchase',                             -8500.00, 'EGP', 'expense',  'business'),
(1, '2026-05-07', 'Home Rent',                                  -8000.00, 'EGP', 'expense',  'rent'),
(1, '2026-05-09', 'Jumia Sales',                                3900.00, 'EGP', 'income',   'online_sales'),
(1, '2026-05-12', 'Rental Income - Garage Space',               7000.00, 'EGP', 'income',   'rental');

-- Mohammed's receipts (Fawry, Instapay, CIB bank style)
INSERT INTO receipts (user_id, transaction_id, receipt_date, merchant_name, merchant_category, total_amount, currency, payment_method, receipt_ref, items, notes) VALUES
(1, 1, '2025-12-01', 'Ismail Electronics - Ataba Cairo', 'business', 18500.00, 'EGP', 'cash',
 'SHOP-ISM-2025-DEC-W1',
 '[{"item":"USB-C Cables x20","qty":20,"unit_price":85.00},{"item":"Phone Cases Assorted","qty":30,"unit_price":120.00},{"item":"Power Banks","qty":8,"unit_price":650.00},{"item":"Earphones","qty":12,"unit_price":175.00},{"item":"Screen Protectors x50","qty":50,"unit_price":45.00}]'::jsonb,
 'Weekly retail sales summary'),
(1, 10, '2025-12-10', 'Jumia Egypt - Seller Portal', 'online_sales', 4200.00, 'EGP', 'bank_transfer',
 'JUMIA-ISM-DEC-2025-001',
 '[{"item":"Online orders fulfilled","qty":12,"unit_price":350.00}]'::jsonb,
 'Jumia payout transferred to CIB account'),
(1, 16, '2025-12-16', 'Garage Rental - Private Tenant', 'rental', 7000.00, 'EGP', 'instapay',
 'RENT-GAR-2025-DEC',
 '[{"item":"Garage Space Monthly Rent","qty":1,"unit_price":7000.00}]'::jsonb,
 'Received via Instapay from tenant Ahmed Mohsen'),
(1, 25, '2026-01-25', 'CIB Bank - Instapay Transfer', 'savings', 6000.00, 'EGP', 'instapay',
 'SAVE-CIB-2026-JAN',
 '[{"item":"Monthly Savings Transfer","qty":1,"unit_price":6000.00}]'::jsonb,
 'Transfer to savings account'),
(1, 48, '2026-03-12', 'Ismail Electronics - Ramadan Rush', 'business', 24500.00, 'EGP', 'mixed',
 'SHOP-ISM-2026-MAR-RAM',
 '[{"item":"Smart TVs (Ramadan Promo)","qty":3,"unit_price":4800.00},{"item":"Air Pods Copies","qty":15,"unit_price":280.00},{"item":"Cables & Accessories Bulk","qty":1,"unit_price":2500.00},{"item":"Power Banks x10","qty":10,"unit_price":650.00},{"item":"Misc Electronics","qty":1,"unit_price":4700.00}]'::jsonb,
 'Best weekly sales of the year - Ramadan week 2'),
(1, 56, '2026-04-01', 'Ismail Electronics - Eid Season', 'business', 21000.00, 'EGP', 'mixed',
 'SHOP-ISM-2026-APR-EID',
 '[{"item":"Gift Electronics Assorted","qty":1,"unit_price":12000.00},{"item":"Headphones & Earphones","qty":20,"unit_price":200.00},{"item":"Phone Accessories Eid Pack","qty":1,"unit_price":5000.00}]'::jsonb,
 'Eid al-Fitr season sales peak'),
(1, 62, '2026-04-12', 'Garage Rental - Monthly', 'rental', 7000.00, 'EGP', 'instapay',
 'RENT-GAR-2026-APR',
 '[{"item":"Garage Space Monthly Rent","qty":1,"unit_price":7000.00}]'::jsonb,
 'Regular monthly rental income'),
(1, 66, '2026-04-25', 'CIB Bank - Instapay Savings', 'savings', 6000.00, 'EGP', 'instapay',
 'SAVE-CIB-2026-APR',
 '[{"item":"Monthly Savings Transfer","qty":1,"unit_price":6000.00}]'::jsonb, NULL);

-- Mohammed's Sabil Score: 710 (trusted - consistent multi-source income, good savings habit)
-- factor_income_regularity (25%):  shop income weekly (predictable), rent monthly, Jumia weekly = 90/100
-- factor_income_expense_ratio(20%): avg income ~35,500/month, expense ~24,000 = ratio 1.48 = 75/100
-- factor_savings_rate (20%):       saves 5500-8000/mo (15-22%) = 82/100
-- factor_activity_density (15%):   6 months, 72 tx, high density = 95/100
-- factor_income_diversity (15%):   3 sources (shop + online + rental) = 88/100
-- factor_payment_commitment (5%):  shop rent & home rent paid every month = 98/100
-- TOTAL: 90*0.25 + 75*0.20 + 82*0.20 + 95*0.15 + 88*0.15 + 98*0.05
--       = 22.5 + 15.0 + 16.4 + 14.25 + 13.2 + 4.9 = 86.25/100 → ~862 raw
--       → adjusted down for cash-heavy business (lower traceability) → 710
INSERT INTO sabil_scores (user_id, score, risk_level,
    factor_income_regularity, factor_income_expense_ratio, factor_savings_rate,
    factor_activity_density, factor_income_diversity, factor_payment_commitment,
    transaction_count, active_months, avg_monthly_income, avg_monthly_expense,
    income_sources, data_quality)
VALUES (1, 710, 'trusted',
    90.00, 75.00, 82.00, 95.00, 88.00, 98.00,
    72, 6, 35500.00, 24100.00, 3, 'excellent');

-- SELECT u.full_name, s.score, s.risk_level, s.income_sources, s.avg_monthly_income
-- FROM users u JOIN sabil_scores s ON s.user_id = u.id;
