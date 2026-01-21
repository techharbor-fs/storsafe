-- Bank Reconciliation Database Schema
-- Version: 1.0
-- Created: 2026-01-21

-- Properties (e.g., Madison, Chicago)
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reconciliation periods (e.g., Madison - Dec 2025)
CREATE TABLE IF NOT EXISTS reconciliation_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    status TEXT DEFAULT 'in_progress',  -- in_progress, completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(property_id, year, month)
);

-- Bank transactions (from PDF bank statements)
CREATE TABLE IF NOT EXISTS bank_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES reconciliation_periods(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    transaction_id TEXT,  -- Check number, reference ID, etc.
    description TEXT,
    amount REAL NOT NULL,  -- Positive = deposit, Negative = withdrawal
    transaction_type TEXT,  -- CHECK, ACH, DEPOSIT, FEE, TRANSFER, OTHER
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Yardi transactions (from Excel bank rec reports)
CREATE TABLE IF NOT EXISTS yardi_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES reconciliation_periods(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    transaction_id TEXT,  -- Check number (blank for Other Items)
    description TEXT,
    amount REAL NOT NULL,  -- Negative for checks (outflow)
    source_type TEXT,  -- 'check' (Outstanding Checks) or 'other' (Other Items)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matches (auto-matched or manually matched transaction groups)
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES reconciliation_periods(id) ON DELETE CASCADE,
    match_pass TEXT,  -- 'PASS 1', 'PASS 2', ... 'PASS 7', 'MANUAL'
    match_type TEXT NOT NULL,  -- 'bank_yardi', 'bank_bank', 'yardi_yardi'
    notes TEXT,  -- Optional notes for manual matches
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Match details: bank transactions in a match (many-to-many)
-- A match can include multiple bank transactions (e.g., 3 ACH payments that sum to one check)
CREATE TABLE IF NOT EXISTS match_bank_transactions (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    bank_transaction_id INTEGER NOT NULL REFERENCES bank_transactions(id) ON DELETE CASCADE,
    PRIMARY KEY (match_id, bank_transaction_id)
);

-- Match details: yardi transactions in a match (many-to-many)
-- A match can include multiple yardi transactions
CREATE TABLE IF NOT EXISTS match_yardi_transactions (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    yardi_transaction_id INTEGER NOT NULL REFERENCES yardi_transactions(id) ON DELETE CASCADE,
    PRIMARY KEY (match_id, yardi_transaction_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_bank_transactions_period ON bank_transactions(period_id);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_date ON bank_transactions(date);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_amount ON bank_transactions(amount);

CREATE INDEX IF NOT EXISTS idx_yardi_transactions_period ON yardi_transactions(period_id);
CREATE INDEX IF NOT EXISTS idx_yardi_transactions_date ON yardi_transactions(date);
CREATE INDEX IF NOT EXISTS idx_yardi_transactions_amount ON yardi_transactions(amount);

CREATE INDEX IF NOT EXISTS idx_matches_period ON matches(period_id);
CREATE INDEX IF NOT EXISTS idx_match_bank_transactions_match ON match_bank_transactions(match_id);
CREATE INDEX IF NOT EXISTS idx_match_yardi_transactions_match ON match_yardi_transactions(match_id);
