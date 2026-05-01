-- ═══════════════════════════════════════════════════════════════════════════
--  SABIL FINANCIAL IDENTITY — YEMEN DATABASE (sabil_ye)
--  User: Naif Falah
--  Currency: YER (Yemeni Rial) — note: 1 USD ≈ 540 YER (2026 est.)
-- ═══════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── SCHEMA (identical structure across all country DBs) ─────────────────────

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    full_name        VARCHAR(120) NOT NULL,
    phone_number     VARCHAR(20)  UNIQUE NOT NULL,
    email            VARCHAR(150) UNIQUE,
    national_id      VARCHAR(50)  NOT NULL,
    nationality      VARCHAR(50)  DEFAULT 'Yemeni',
    country_code     CHAR(2)      DEFAULT 'YE',
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
    currency    CHAR(3)       DEFAULT 'YER',
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id               SERIAL PRIMARY KEY,
    user_id          INT REFERENCES users(id) ON DELETE CASCADE,
    transaction_date DATE          NOT NULL,
    description      VARCHAR(255)  NOT NULL,
    amount           NUMERIC(14,2) NOT NULL,
    currency         CHAR(3)       DEFAULT 'YER',
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
    currency          CHAR(3)       DEFAULT 'YER',
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
--  SEED DATA — NAIF FALAH
--  Profile: Informal trader + family remittances, irregular cash economy
--  Context: Yemen financial system is fragmented (two central banks since 2016)
--  Income: Mix of small trade, remittances from Saudi Arabia, cash economy
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO users (full_name, phone_number, email, national_id, nationality, country_code,
                   date_of_birth, gender, is_active, kyc_verified, kyc_verified_at, onboarding_step)
VALUES ('Naif Falah', '+967771234567', 'naif.falah@ye.sabil.app',
        'YE-199205-0321', 'Yemeni', 'YE', '1992-05-10', 'M',
        TRUE, TRUE, NOW() - INTERVAL '45 days', 3);

INSERT INTO wallets (user_id, balance, currency)
VALUES (1, 185000.00, 'YER');

-- Naif's transactions (Jan-May 2026) — irregular income, cash-heavy economy
-- Note: amounts in YER. ~540 YER = 1 USD
INSERT INTO transactions (user_id, transaction_date, description, amount, currency, type, category) VALUES
-- January (bad start, slow trade)
(1, '2026-01-04', 'Family Remittance from KSA (Brother)',   270000.00, 'YER', 'income',   'remittance'),
(1, '2026-01-06', 'Rent - Sanaa House',                    -108000.00, 'YER', 'expense',  'rent'),
(1, '2026-01-08', 'Market Goods Purchase (stock)',          -54000.00, 'YER', 'expense',  'business'),
(1, '2026-01-10', 'Market Sales Income',                     81000.00, 'YER', 'income',   'trade'),
(1, '2026-01-14', 'Groceries - Weekly',                     -21600.00, 'YER', 'expense',  'groceries'),
(1, '2026-01-18', 'Fuel - Generator (electricity backup)',   -16200.00, 'YER', 'expense',  'utilities'),
(1, '2026-01-20', 'Mobile Money Top-up',                     -5400.00, 'YER', 'expense',  'telecom'),
(1, '2026-01-22', 'Market Sales Income',                     43200.00, 'YER', 'income',   'trade'),
(1, '2026-01-28', 'Groceries',                              -18900.00, 'YER', 'expense',  'groceries'),
-- February (slightly better, remittance arrived late)
(1, '2026-02-03', 'Market Goods Purchase',                  -43200.00, 'YER', 'expense',  'business'),
(1, '2026-02-05', 'Market Sales - Good Week',               108000.00, 'YER', 'income',   'trade'),
(1, '2026-02-07', 'Rent - Sanaa House',                    -108000.00, 'YER', 'expense',  'rent'),
(1, '2026-02-10', 'Groceries',                              -21600.00, 'YER', 'expense',  'groceries'),
(1, '2026-02-14', 'Family Remittance from KSA',             216000.00, 'YER', 'income',   'remittance'),
(1, '2026-02-16', 'Medical - Child Clinic',                 -13500.00, 'YER', 'expense',  'health'),
(1, '2026-02-20', 'Market Sales',                            54000.00, 'YER', 'income',   'trade'),
(1, '2026-02-24', 'Fuel & Transport',                       -21600.00, 'YER', 'expense',  'transport'),
(1, '2026-02-28', 'Small Savings - Cash at Home',           -27000.00, 'YER', 'saving',   'savings'),
-- March (good trade month)
(1, '2026-03-02', 'Market Goods - Bulk Purchase',           -81000.00, 'YER', 'expense',  'business'),
(1, '2026-03-05', 'Market Sales - Ramadan Prep',            162000.00, 'YER', 'income',   'trade'),
(1, '2026-03-07', 'Rent - Sanaa House',                    -108000.00, 'YER', 'expense',  'rent'),
(1, '2026-03-10', 'Groceries',                              -27000.00, 'YER', 'expense',  'groceries'),
(1, '2026-03-12', 'Market Sales',                            97200.00, 'YER', 'income',   'trade'),
(1, '2026-03-15', 'Family Remittance from KSA',             270000.00, 'YER', 'income',   'remittance'),
(1, '2026-03-18', 'Fuel & Generator',                       -16200.00, 'YER', 'expense',  'utilities'),
(1, '2026-03-22', 'Eid Goods Purchase',                     -54000.00, 'YER', 'expense',  'shopping'),
(1, '2026-03-28', 'Market Sales - Eid Season',              135000.00, 'YER', 'income',   'trade'),
-- April (post-Eid slowdown)
(1, '2026-04-03', 'Market Goods Purchase',                  -43200.00, 'YER', 'expense',  'business'),
(1, '2026-04-06', 'Market Sales',                            59400.00, 'YER', 'income',   'trade'),
(1, '2026-04-07', 'Rent - Sanaa House',                    -108000.00, 'YER', 'expense',  'rent'),
(1, '2026-04-12', 'Groceries',                              -21600.00, 'YER', 'expense',  'groceries'),
(1, '2026-04-16', 'Mobile Money - Casual Transfer Out',     -16200.00, 'YER', 'transfer', 'transfer'),
(1, '2026-04-20', 'Fuel & Utilities',                       -18900.00, 'YER', 'expense',  'utilities'),
(1, '2026-04-25', 'Market Sales',                            40500.00, 'YER', 'income',   'trade'),
-- May (current)
(1, '2026-05-01', 'Family Remittance from KSA',             216000.00, 'YER', 'income',   'remittance'),
(1, '2026-05-03', 'Rent - Sanaa House',                    -108000.00, 'YER', 'expense',  'rent'),
(1, '2026-05-05', 'Market Goods Purchase',                  -37800.00, 'YER', 'expense',  'business');

-- Naif's receipts
INSERT INTO receipts (user_id, transaction_id, receipt_date, merchant_name, merchant_category, total_amount, currency, payment_method, receipt_ref, items, notes) VALUES
(1, 4, '2026-01-10', 'Sanaa Central Market', 'trade', 81000.00, 'YER', 'cash',
 'MKT-SAN-2026-001',
 '[{"item":"Household goods resale","qty":1,"unit_price":81000.00}]'::jsonb,
 'Weekly market sales, cash collected'),
(1, 8, '2026-01-14', 'Al-Hasab Grocery', 'groceries', 21600.00, 'YER', 'cash',
 'GRC-AH-2026-001',
 '[{"item":"Rice 10kg","qty":2,"unit_price":5400.00},{"item":"Oil","qty":2,"unit_price":2700.00},{"item":"Sugar","qty":3,"unit_price":1800.00},{"item":"Mixed Vegetables","qty":1,"unit_price":2700.00}]'::jsonb, NULL),
(1, 16, '2026-02-14', 'STC/MTN Mobile Wallet - KSA Transfer', 'remittance', 216000.00, 'YER', 'mobile_wallet',
 'RMT-KSA-2026-002',
 '[{"item":"International Remittance","qty":1,"unit_price":216000.00}]'::jsonb,
 'Received from brother Ahmed Falah in Riyadh'),
(1, 21, '2026-03-05', 'Sanaa Wholesale Market - Ramadan Stock', 'trade', 162000.00, 'YER', 'cash',
 'MKT-SAN-2026-008',
 '[{"item":"Ramadan food goods bulk","qty":1,"unit_price":162000.00}]'::jsonb, NULL),
(1, 25, '2026-03-15', 'Western Union / MTN Money', 'remittance', 270000.00, 'YER', 'mobile_wallet',
 'RMT-KSA-2026-003',
 '[{"item":"International Remittance","qty":1,"unit_price":270000.00}]'::jsonb,
 'Received via Western Union Sanaa branch');

-- Naif's Sabil Score: 480 (moderate-low)
-- Irregular income timing, cash-heavy, 2 income sources (remittance + trade)
-- but good rent payment and improving trend
-- factor_income_regularity (25%):  remittances come 1-2x/month, trade varies = 45/100
-- factor_income_expense_ratio(20%): income ~278k YER/mo, expense ~188k YER/mo, ratio 1.48 = 72/100
-- factor_savings_rate (20%):       only saved once (March miss) = 30/100
-- factor_activity_density (15%):   5 months, 38 tx, ok density = 70/100
-- factor_income_diversity (15%):   2 sources (remittance + trade) = 65/100
-- factor_payment_commitment (5%):  rent paid monthly (slightly late sometimes) = 75/100
INSERT INTO sabil_scores (user_id, score, risk_level,
    factor_income_regularity, factor_income_expense_ratio, factor_savings_rate,
    factor_activity_density, factor_income_diversity, factor_payment_commitment,
    transaction_count, active_months, avg_monthly_income, avg_monthly_expense,
    income_sources, data_quality)
VALUES (1, 480, 'moderate',
    45.00, 72.00, 30.00, 70.00, 65.00, 75.00,
    38, 5, 278100.00, 188100.00, 2, 'moderate');

-- SELECT u.full_name, s.score, s.risk_level FROM users u JOIN sabil_scores s ON s.user_id = u.id;
