-- ═══════════════════════════════════════════════════════════════════════════
--  SABIL FINANCIAL IDENTITY — LIBYA DATABASE (sabil_ly)
--  Users: Salih Otman, Isra Issa
--  Currency: LYD (Libyan Dinar)
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── Extensions ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── SCHEMA ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    full_name        VARCHAR(120) NOT NULL,
    phone_number     VARCHAR(20)  UNIQUE NOT NULL,
    email            VARCHAR(150) UNIQUE,
    national_id      VARCHAR(50)  NOT NULL,
    nationality      VARCHAR(50)  DEFAULT 'Libyan',
    country_code     CHAR(2)      DEFAULT 'LY',
    date_of_birth    DATE,
    gender           CHAR(1),            -- M / F
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
    currency    CHAR(3)       DEFAULT 'LYD',
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id               SERIAL PRIMARY KEY,
    user_id          INT REFERENCES users(id) ON DELETE CASCADE,
    transaction_date DATE          NOT NULL,
    description      VARCHAR(255)  NOT NULL,
    amount           NUMERIC(14,2) NOT NULL,   -- positive = income, negative = expense
    currency         CHAR(3)       DEFAULT 'LYD',
    type             VARCHAR(20)   NOT NULL CHECK (type IN ('income','expense','transfer','saving')),
    category         VARCHAR(50),
    source           VARCHAR(30)   DEFAULT 'bank_statement',
    confidence       NUMERIC(4,3)  DEFAULT 1.000,
    created_at       TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receipts (
    id               SERIAL PRIMARY KEY,
    user_id          INT REFERENCES users(id) ON DELETE CASCADE,
    transaction_id   INT REFERENCES transactions(id) ON DELETE SET NULL,
    receipt_date     DATE          NOT NULL,
    merchant_name    VARCHAR(120),
    merchant_category VARCHAR(60),
    total_amount     NUMERIC(14,2) NOT NULL,
    currency         CHAR(3)       DEFAULT 'LYD',
    payment_method   VARCHAR(30)   DEFAULT 'cash',   -- cash, card, transfer
    receipt_ref      VARCHAR(60),
    items            JSONB,                           -- line-items JSON array
    notes            TEXT,
    created_at       TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sabil_scores (
    id                     SERIAL PRIMARY KEY,
    user_id                INT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    score                  SMALLINT      NOT NULL CHECK (score BETWEEN 0 AND 1000),
    risk_level             VARCHAR(20)   NOT NULL, -- trusted, low, moderate, high, risky
    -- factor breakdown (0-100 each, weighted)
    factor_income_regularity   NUMERIC(5,2), -- 25%
    factor_income_expense_ratio NUMERIC(5,2), -- 20%
    factor_savings_rate        NUMERIC(5,2), -- 20%
    factor_activity_density    NUMERIC(5,2), -- 15%
    factor_income_diversity    NUMERIC(5,2), -- 15%
    factor_payment_commitment  NUMERIC(5,2), -- 5%
    -- metadata
    transaction_count      INT,
    active_months          INT,
    avg_monthly_income     NUMERIC(14,2),
    avg_monthly_expense    NUMERIC(14,2),
    income_sources         INT,
    data_quality           VARCHAR(20)   DEFAULT 'good',
    is_active              BOOLEAN       DEFAULT TRUE,
    computed_at            TIMESTAMPTZ   DEFAULT NOW(),
    updated_at             TIMESTAMPTZ   DEFAULT NOW()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────
CREATE INDEX idx_transactions_user_date ON transactions(user_id, transaction_date DESC);
CREATE INDEX idx_receipts_user_date     ON receipts(user_id, receipt_date DESC);

-- ═══════════════════════════════════════════════════════════════════════════
--  SEED DATA — SALIH OTMAN (Government Employee, stable income)
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO users (full_name, phone_number, email, national_id, nationality, country_code,
                   date_of_birth, gender, is_active, kyc_verified, kyc_verified_at, onboarding_step)
VALUES ('Salih Otman', '+218912345678', 'salih.otman@ly.sabil.app',
        'LY-198803-0044', 'Libyan', 'LY', '1988-03-15', 'M',
        TRUE, TRUE, NOW() - INTERVAL '30 days', 3);

INSERT INTO wallets (user_id, balance, currency)
VALUES (1, 4250.00, 'LYD');

-- Salih's 6 months of transactions (Jan-Jun 2026)
INSERT INTO transactions (user_id, transaction_date, description, amount, currency, type, category) VALUES
-- January
(1, '2026-01-01', 'Government Salary - January',       5200.00, 'LYD', 'income',   'salary'),
(1, '2026-01-03', 'Supermarket Alshabab',               -310.00, 'LYD', 'expense',  'groceries'),
(1, '2026-01-05', 'Electricity & Water Bill',            -180.00, 'LYD', 'expense',  'utilities'),
(1, '2026-01-08', 'Private Tutoring Fees Received',      800.00, 'LYD', 'income',   'freelance'),
(1, '2026-01-10', 'Rent - Tripoli Apartment',           -1200.00, 'LYD', 'expense',  'rent'),
(1, '2026-01-14', 'Mobile Top-up',                       -50.00, 'LYD', 'expense',  'telecom'),
(1, '2026-01-18', 'Pharmacy',                            -95.00, 'LYD', 'expense',  'health'),
(1, '2026-01-22', 'Children School Fees',               -400.00, 'LYD', 'expense',  'education'),
(1, '2026-01-28', 'Savings Transfer to Family',         -600.00, 'LYD', 'saving',   'savings'),
(1, '2026-01-30', 'Fuel & Transportation',               -120.00, 'LYD', 'expense',  'transport'),
-- February
(1, '2026-02-01', 'Government Salary - February',       5200.00, 'LYD', 'income',   'salary'),
(1, '2026-02-03', 'Supermarket Alshabab',               -290.00, 'LYD', 'expense',  'groceries'),
(1, '2026-02-05', 'Electricity & Water Bill',            -165.00, 'LYD', 'expense',  'utilities'),
(1, '2026-02-08', 'Private Tutoring Fees Received',      900.00, 'LYD', 'income',   'freelance'),
(1, '2026-02-10', 'Rent - Tripoli Apartment',           -1200.00, 'LYD', 'expense',  'rent'),
(1, '2026-02-15', 'Restaurant Al-Saraya',                -150.00, 'LYD', 'expense',  'food'),
(1, '2026-02-20', 'Clothing Shopping',                   -220.00, 'LYD', 'expense',  'shopping'),
(1, '2026-02-25', 'Internet Subscription',               -80.00, 'LYD', 'expense',  'telecom'),
(1, '2026-02-28', 'Savings Transfer',                   -700.00, 'LYD', 'saving',   'savings'),
-- March
(1, '2026-03-01', 'Government Salary - March',          5200.00, 'LYD', 'income',   'salary'),
(1, '2026-03-04', 'Supermarket',                         -340.00, 'LYD', 'expense',  'groceries'),
(1, '2026-03-06', 'Electricity & Water Bill',            -190.00, 'LYD', 'expense',  'utilities'),
(1, '2026-03-08', 'Private Tutoring - 3 Students',      1100.00, 'LYD', 'income',   'freelance'),
(1, '2026-03-10', 'Rent - Tripoli Apartment',           -1200.00, 'LYD', 'expense',  'rent'),
(1, '2026-03-16', 'Fuel & Transportation',               -140.00, 'LYD', 'expense',  'transport'),
(1, '2026-03-20', 'Medical Checkup',                     -110.00, 'LYD', 'expense',  'health'),
(1, '2026-03-25', 'Children Activities',                 -200.00, 'LYD', 'expense',  'education'),
(1, '2026-03-30', 'Savings Transfer',                   -800.00, 'LYD', 'saving',   'savings'),
-- April
(1, '2026-04-01', 'Government Salary - April',          5200.00, 'LYD', 'income',   'salary'),
(1, '2026-04-03', 'Supermarket',                         -300.00, 'LYD', 'expense',  'groceries'),
(1, '2026-04-05', 'Electricity & Water Bill',            -175.00, 'LYD', 'expense',  'utilities'),
(1, '2026-04-07', 'Private Tutoring - Ramadan Special',  700.00, 'LYD', 'income',   'freelance'),
(1, '2026-04-10', 'Rent - Tripoli Apartment',           -1200.00, 'LYD', 'expense',  'rent'),
(1, '2026-04-12', 'Eid Gifts & Shopping',               -550.00, 'LYD', 'expense',  'shopping'),
(1, '2026-04-20', 'Charity / Zakat',                    -250.00, 'LYD', 'expense',  'charity'),
(1, '2026-04-28', 'Savings Transfer',                   -600.00, 'LYD', 'saving',   'savings'),
-- May
(1, '2026-05-01', 'Government Salary - May',            5200.00, 'LYD', 'income',   'salary'),
(1, '2026-05-02', 'Supermarket',                         -320.00, 'LYD', 'expense',  'groceries'),
(1, '2026-05-04', 'Electricity & Water Bill',            -185.00, 'LYD', 'expense',  'utilities'),
(1, '2026-05-06', 'Private Tutoring Fees',               950.00, 'LYD', 'income',   'freelance'),
(1, '2026-05-10', 'Rent - Tripoli Apartment',           -1200.00, 'LYD', 'expense',  'rent');

-- Salih's receipts
INSERT INTO receipts (user_id, transaction_id, receipt_date, merchant_name, merchant_category, total_amount, currency, payment_method, receipt_ref, items) VALUES
(1, 3, '2026-01-03', 'Supermarket Alshabab', 'groceries', 310.00, 'LYD', 'cash',
 'RCP-LY-2026-0001',
 '[{"item":"Rice 5kg","qty":2,"unit_price":25.00},{"item":"Cooking Oil","qty":3,"unit_price":18.00},{"item":"Sugar","qty":2,"unit_price":12.00},{"item":"Vegetables","qty":1,"unit_price":45.00},{"item":"Meat 2kg","qty":1,"unit_price":140.00},{"item":"Dairy","qty":1,"unit_price":35.00}]'::jsonb),
(1, 5, '2026-01-05', 'GECOL - General Electric Company of Libya', 'utilities', 180.00, 'LYD', 'bank_transfer',
 'GECOL-2026-001-LY',
 '[{"item":"Electricity January","qty":1,"unit_price":130.00},{"item":"Water Bill","qty":1,"unit_price":50.00}]'::jsonb),
(1, 8, '2026-01-10', 'Al-Noor Private School', 'education', 400.00, 'LYD', 'cash',
 'SCH-2026-JAN-001',
 '[{"item":"Tuition - Child 1","qty":1,"unit_price":200.00},{"item":"Tuition - Child 2","qty":1,"unit_price":200.00}]'::jsonb),
(1, 11, '2026-02-01', 'Supermarket Alshabab', 'groceries', 290.00, 'LYD', 'cash',
 'RCP-LY-2026-0002',
 '[{"item":"Rice 5kg","qty":2,"unit_price":25.00},{"item":"Cooking Oil","qty":2,"unit_price":18.00},{"item":"Bread","qty":5,"unit_price":5.00},{"item":"Vegetables","qty":1,"unit_price":50.00},{"item":"Meat 2kg","qty":1,"unit_price":145.00},{"item":"Dairy","qty":1,"unit_price":22.00}]'::jsonb),
(1, 15, '2026-02-15', 'Restaurant Al-Saraya', 'food', 150.00, 'LYD', 'cash',
 'RST-2026-0044',
 '[{"item":"Family Meal Set","qty":1,"unit_price":120.00},{"item":"Beverages","qty":4,"unit_price":7.50}]'::jsonb);

-- Salih's Sabil Score: 742 (trusted - stable govt + freelance, good savings rate)
-- Factor calculation:
--   income_regularity (25%):  salary hits day-1 every month = 98/100 → 98*0.25 = 24.5
--   income_expense_ratio(20%): avg income 6150, avg expense 3700 = ratio 1.66 → 85/100 → 17.0
--   savings_rate (20%):        saves ~650/month avg, 10.6% of income → 72/100 → 14.4
--   activity_density (15%):    5 months, 43 tx → 88/100 → 13.2
--   income_diversity (15%):    2 sources (salary+freelance) → 70/100 → 10.5
--   payment_commitment (5%):   rent paid every month, bills regular → 95/100 → 4.75
--   TOTAL ≈ 84.35/100 → 843/1000 → adjusted for diversity penalty → 742
INSERT INTO sabil_scores (user_id, score, risk_level,
    factor_income_regularity, factor_income_expense_ratio, factor_savings_rate,
    factor_activity_density, factor_income_diversity, factor_payment_commitment,
    transaction_count, active_months, avg_monthly_income, avg_monthly_expense,
    income_sources, data_quality)
VALUES (1, 742, 'trusted',
    98.00, 85.00, 72.00, 88.00, 70.00, 95.00,
    43, 5, 6150.00, 3710.00, 2, 'excellent');

-- ═══════════════════════════════════════════════════════════════════════════
--  SEED DATA — ISRA ISSA (Part-time freelancer, irregular but improving)
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO users (full_name, phone_number, email, national_id, nationality, country_code,
                   date_of_birth, gender, is_active, kyc_verified, kyc_verified_at, onboarding_step)
VALUES ('Isra Issa', '+218923456789', 'isra.issa@ly.sabil.app',
        'LY-199507-0187', 'Libyan', 'LY', '1995-07-22', 'F',
        TRUE, TRUE, NOW() - INTERVAL '15 days', 3);

INSERT INTO wallets (user_id, balance, currency)
VALUES (2, 1820.00, 'LYD');

-- Isra's transactions (Jan-May 2026) — part-time designer, irregular income
INSERT INTO transactions (user_id, transaction_date, description, amount, currency, type, category) VALUES
-- January (slow start)
(2, '2026-01-05', 'Freelance Logo Design - Client A',   1200.00, 'LYD', 'income',   'freelance'),
(2, '2026-01-07', 'Rent - Shared Apartment',            -600.00, 'LYD', 'expense',  'rent'),
(2, '2026-01-10', 'Groceries',                          -180.00, 'LYD', 'expense',  'groceries'),
(2, '2026-01-12', 'Internet & Tools Subscription',       -90.00, 'LYD', 'expense',  'telecom'),
(2, '2026-01-18', 'Utilities',                          -110.00, 'LYD', 'expense',  'utilities'),
(2, '2026-01-25', 'Freelance Social Media Package',      650.00, 'LYD', 'income',   'freelance'),
(2, '2026-01-28', 'Clothing & Personal Care',           -200.00, 'LYD', 'expense',  'shopping'),
-- February (better month)
(2, '2026-02-03', 'Freelance Branding Project',         1800.00, 'LYD', 'income',   'freelance'),
(2, '2026-02-05', 'Rent - Shared Apartment',            -600.00, 'LYD', 'expense',  'rent'),
(2, '2026-02-08', 'Groceries',                          -195.00, 'LYD', 'expense',  'groceries'),
(2, '2026-02-10', 'Part-time Teaching at NGO',           400.00, 'LYD', 'income',   'salary'),
(2, '2026-02-12', 'Internet & Tools',                    -90.00, 'LYD', 'expense',  'telecom'),
(2, '2026-02-18', 'Utilities',                          -105.00, 'LYD', 'expense',  'utilities'),
(2, '2026-02-22', 'Small Savings',                      -300.00, 'LYD', 'saving',   'savings'),
-- March (average)
(2, '2026-03-02', 'Freelance Web Design',                900.00, 'LYD', 'income',   'freelance'),
(2, '2026-03-05', 'Rent - Shared Apartment',            -600.00, 'LYD', 'expense',  'rent'),
(2, '2026-03-09', 'Groceries',                          -170.00, 'LYD', 'expense',  'groceries'),
(2, '2026-03-12', 'Part-time Teaching at NGO',           400.00, 'LYD', 'income',   'salary'),
(2, '2026-03-14', 'Medical Visit',                       -80.00, 'LYD', 'expense',  'health'),
(2, '2026-03-20', 'Internet & Tools',                    -90.00, 'LYD', 'expense',  'telecom'),
(2, '2026-03-22', 'Utilities',                          -120.00, 'LYD', 'expense',  'utilities'),
(2, '2026-03-28', 'Freelance Emergency Fix',             350.00, 'LYD', 'income',   'freelance'),
-- April (strong month)
(2, '2026-04-01', 'Freelance UI/UX Project - Major',    2400.00, 'LYD', 'income',   'freelance'),
(2, '2026-04-05', 'Rent - Shared Apartment',            -600.00, 'LYD', 'expense',  'rent'),
(2, '2026-04-08', 'Groceries & Eid Shopping',           -350.00, 'LYD', 'expense',  'groceries'),
(2, '2026-04-10', 'Part-time Teaching',                  400.00, 'LYD', 'income',   'salary'),
(2, '2026-04-15', 'Software License Annual',            -250.00, 'LYD', 'expense',  'telecom'),
(2, '2026-04-20', 'Utilities',                          -110.00, 'LYD', 'expense',  'utilities'),
(2, '2026-04-25', 'Savings Transfer',                   -500.00, 'LYD', 'saving',   'savings'),
-- May (current)
(2, '2026-05-01', 'Freelance Logo Batch - 3 Clients',   1100.00, 'LYD', 'income',   'freelance'),
(2, '2026-05-03', 'Rent - Shared Apartment',            -600.00, 'LYD', 'expense',  'rent'),
(2, '2026-05-05', 'Groceries',                          -160.00, 'LYD', 'expense',  'groceries');

-- Isra's receipts
INSERT INTO receipts (user_id, transaction_id, receipt_date, merchant_name, merchant_category, total_amount, currency, payment_method, receipt_ref, items) VALUES
(2, 48, '2026-01-05', 'Fiverr / Direct Client - Client A', 'freelance', 1200.00, 'LYD', 'bank_transfer',
 'INV-ISRA-2026-001',
 '[{"item":"Logo Design Package","qty":1,"unit_price":1200.00}]'::jsonb),
(2, 53, '2026-01-25', 'Instagram Client - Social Media', 'freelance', 650.00, 'LYD', 'bank_transfer',
 'INV-ISRA-2026-002',
 '[{"item":"Social Media Pack 10 posts","qty":1,"unit_price":650.00}]'::jsonb),
(2, 55, '2026-02-03', 'Startup Branding Project', 'freelance', 1800.00, 'LYD', 'bank_transfer',
 'INV-ISRA-2026-003',
 '[{"item":"Brand Identity Full Package","qty":1,"unit_price":1800.00}]'::jsonb),
(2, 70, '2026-04-01', 'Tech Company UI/UX Redesign', 'freelance', 2400.00, 'LYD', 'bank_transfer',
 'INV-ISRA-2026-007',
 '[{"item":"UI/UX Design - 20 Screens","qty":1,"unit_price":1800.00},{"item":"Prototype & Handoff","qty":1,"unit_price":600.00}]'::jsonb);

-- Isra's Sabil Score: 590 (moderate - freelance only, improving trend, good rent commitment)
INSERT INTO sabil_scores (user_id, score, risk_level,
    factor_income_regularity, factor_income_expense_ratio, factor_savings_rate,
    factor_activity_density, factor_income_diversity, factor_payment_commitment,
    transaction_count, active_months, avg_monthly_income, avg_monthly_expense,
    income_sources, data_quality)
VALUES (2, 590, 'moderate',
    55.00, 68.00, 48.00, 75.00, 60.00, 85.00,
    33, 5, 1757.00, 1268.00, 2, 'good');

-- ─── Verification queries (commented out, run manually) ─────────────────────
-- SELECT u.full_name, s.score, s.risk_level, s.avg_monthly_income, s.avg_monthly_expense
-- FROM users u JOIN sabil_scores s ON s.user_id = u.id;
--
-- SELECT u.full_name, COUNT(t.id) AS tx_count, SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS total_income
-- FROM users u JOIN transactions t ON t.user_id = u.id GROUP BY u.full_name;
--
-- SELECT u.full_name, r.merchant_name, r.total_amount, r.payment_method
-- FROM users u JOIN receipts r ON r.user_id = u.id ORDER BY r.receipt_date;
