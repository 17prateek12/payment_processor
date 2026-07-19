--Merchant
CREATE TABLE IF NOT EXISTS merchants(
    id VARCHAR(100) PRIMARY KEY,
    merchant_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

--transaction
CREATE TABLE IF NOT EXISTS transactions(
    id VARCHAR(100) PRIMARY KEY,
    merchant_id VARCHAR(100) NOT NULL REFERENCES merchants(id),
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    settlement_status VARCHAR(20) NOT NULL DEFAULT 'unsettled',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL   
);

-- Migration query: ensure version column exists if table is already created
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

--event
CREATE TABLE IF NOT EXISTS events(
    event_id VARCHAR(100) PRIMARY KEY,
    transaction_id VARCHAR(100) NOT NULL REFERENCES transactions(id),
    event_type VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT NOW()
);

--========================================================================================
--INDEX
--========================================================================================

CREATE INDEX IF NOT EXISTS idx_transactions_merchant_status_date ON transactions(merchant_id, payment_status, created_at);
CREATE INDEX IF NOT EXISTS idx_events_transaction_id ON events(transaction_id);