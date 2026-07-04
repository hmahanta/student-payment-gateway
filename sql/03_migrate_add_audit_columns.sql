-- =============================================================================
-- Script Name : 03_migrate_add_audit_columns.sql
-- Purpose     : Non-breaking migration — adds enterprise audit columns
--               (created_by, created_date, updated_by, updated_date,
--               record_status) to the 3 tables already created and
--               populated by 01_create_tables.sql / 02_seed_sample_data.sql.
--
--               Uses ADD COLUMN ... DEFAULT so existing rows are backfilled
--               automatically — no existing data is altered or lost.
--
-- Author      : Harish
-- Run Order   : AFTER 01_create_tables.sql + 02_seed_sample_data.sql,
--               BEFORE 04_create_enterprise_tables.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- STUDENTS
-- -----------------------------------------------------------------------------
ALTER TABLE students ADD (
    created_by      VARCHAR2(50)  DEFAULT 'SYSTEM' NOT NULL,
    updated_by      VARCHAR2(50),
    record_status   VARCHAR2(20)  DEFAULT 'ACTIVE' NOT NULL
);

ALTER TABLE students ADD CONSTRAINT ck_students_rec_status
    CHECK (record_status IN ('ACTIVE', 'INACTIVE'));

COMMENT ON COLUMN students.created_by IS 'User/system that created this row (enterprise audit trail)';
COMMENT ON COLUMN students.record_status IS 'Soft-delete / lifecycle flag, distinct from is_active business flag';

-- Note: created_at/updated_at already exist from 01_create_tables.sql and
-- serve as created_date/updated_date — not duplicated here.

-- -----------------------------------------------------------------------------
-- FEE_INVOICES
-- -----------------------------------------------------------------------------
ALTER TABLE fee_invoices ADD (
    created_by      VARCHAR2(50)  DEFAULT 'SYSTEM' NOT NULL,
    updated_by      VARCHAR2(50),
    record_status   VARCHAR2(20)  DEFAULT 'ACTIVE' NOT NULL
);

ALTER TABLE fee_invoices ADD CONSTRAINT ck_invoices_rec_status
    CHECK (record_status IN ('ACTIVE', 'INACTIVE'));

-- -----------------------------------------------------------------------------
-- PAYMENT_TRANSACTIONS
-- -----------------------------------------------------------------------------
ALTER TABLE payment_transactions ADD (
    created_by       VARCHAR2(50)  DEFAULT 'SYSTEM' NOT NULL,
    updated_by       VARCHAR2(50),
    record_status    VARCHAR2(20)  DEFAULT 'ACTIVE' NOT NULL,
    gateway_code      VARCHAR2(30),
    idempotency_key    VARCHAR2(64),
    correlation_id      VARCHAR2(64)
);

ALTER TABLE payment_transactions ADD CONSTRAINT ck_txn_rec_status
    CHECK (record_status IN ('ACTIVE', 'INACTIVE'));

ALTER TABLE payment_transactions ADD CONSTRAINT uq_txn_idempotency
    UNIQUE (idempotency_key);

COMMENT ON COLUMN payment_transactions.gateway_code IS 'FK to payment_gateway_config — which adapter processed this transaction (added FK constraint in 04_create_enterprise_tables.sql once that table exists)';
COMMENT ON COLUMN payment_transactions.idempotency_key IS 'Client-supplied key preventing duplicate payment initiation on retry';
COMMENT ON COLUMN payment_transactions.correlation_id IS 'Correlation ID threading this transaction through structured logs across services';

CREATE INDEX ix_txn_idempotency ON payment_transactions (idempotency_key);
CREATE INDEX ix_txn_correlation ON payment_transactions (correlation_id);

COMMIT;
