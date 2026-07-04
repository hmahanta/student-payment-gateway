-- =============================================================================
-- Script Name : 04_create_enterprise_tables.sql
-- Purpose     : Creates the 5 new enterprise tables — PAYMENT_AUDIT,
--               PAYMENT_STATUS_HISTORY, PAYMENT_GATEWAY_CONFIG,
--               PAYMENT_WEBHOOK_LOG, SYSTEM_PARAMETERS — plus the FK from
--               payment_transactions.gateway_code added in the prior
--               migration script.
--
-- Author      : Harish
-- Run Order   : AFTER 03_migrate_add_audit_columns.sql
-- Notes       : Oracle XE compatible. Surrogate numeric keys use classic
--               SEQUENCE + BEFORE INSERT TRIGGER (rather than IDENTITY
--               columns) for portability across XE 18c/21c.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Table: PAYMENT_GATEWAY_CONFIG
-- Adapter registry — one row per payment gateway/adapter the Payment
-- Orchestrator can dispatch to (Mock Bank today; Razorpay/PhonePe/etc.
-- later, added as rows here, never as code changes to the orchestrator).
-- -----------------------------------------------------------------------------
CREATE TABLE payment_gateway_config (
    gateway_code     VARCHAR2(30)   NOT NULL,
    gateway_name      VARCHAR2(100)  NOT NULL,
    adapter_class      VARCHAR2(150)  NOT NULL,
    is_enabled           NUMBER(1)      DEFAULT 1 NOT NULL,
    config_json            CLOB,
    created_by                VARCHAR2(50)   DEFAULT 'SYSTEM' NOT NULL,
    created_date                TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    updated_by                    VARCHAR2(50),
    updated_date                    TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    record_status                     VARCHAR2(20)   DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_gateway_config PRIMARY KEY (gateway_code),
    CONSTRAINT ck_gateway_enabled CHECK (is_enabled IN (0, 1)),
    CONSTRAINT ck_gateway_rec_status CHECK (record_status IN ('ACTIVE', 'INACTIVE'))
);

COMMENT ON TABLE payment_gateway_config IS 'Registry of payment gateway adapters (Adapter Pattern) — add a row to onboard a new provider, no code change';
COMMENT ON COLUMN payment_gateway_config.adapter_class IS 'Fully qualified Python class implementing PaymentGatewayAdapter for this gateway_code';
COMMENT ON COLUMN payment_gateway_config.config_json IS 'Adapter-specific settings (base_url, timeout_seconds, merchant_id, etc.) as JSON text';

-- Now that payment_gateway_config exists, wire up the FK deferred from the
-- prior migration script.
ALTER TABLE payment_transactions ADD CONSTRAINT fk_txn_gateway
    FOREIGN KEY (gateway_code) REFERENCES payment_gateway_config (gateway_code);

-- -----------------------------------------------------------------------------
-- Table: PAYMENT_STATUS_HISTORY
-- Every status transition a transaction goes through (PENDING -> SUCCESS,
-- PENDING -> FAILED, etc.) — separate from PAYMENT_AUDIT, which covers
-- general entity changes, not just status transitions.
-- -----------------------------------------------------------------------------
CREATE SEQUENCE seq_payment_status_history START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE payment_status_history (
    history_id       NUMBER(19)     NOT NULL,
    transaction_id    VARCHAR2(30)   NOT NULL,
    old_status         VARCHAR2(20),
    new_status           VARCHAR2(20)   NOT NULL,
    changed_by             VARCHAR2(50)   DEFAULT 'SYSTEM' NOT NULL,
    changed_at               TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    remarks                    VARCHAR2(255),
    correlation_id               VARCHAR2(64),
    CONSTRAINT pk_status_history PRIMARY KEY (history_id),
    CONSTRAINT fk_history_txn FOREIGN KEY (transaction_id)
        REFERENCES payment_transactions (transaction_id)
);

CREATE OR REPLACE TRIGGER trg_status_history_pk
BEFORE INSERT ON payment_status_history
FOR EACH ROW
WHEN (NEW.history_id IS NULL)
BEGIN
    :NEW.history_id := seq_payment_status_history.NEXTVAL;
END;
/

CREATE INDEX ix_history_txn ON payment_status_history (transaction_id);

COMMENT ON TABLE payment_status_history IS 'Full status-transition timeline per transaction, powering the frontend Transaction Timeline view';

-- -----------------------------------------------------------------------------
-- Table: PAYMENT_AUDIT
-- General-purpose entity audit trail (insert/update/field-level changes)
-- across STUDENTS, FEE_INVOICES, PAYMENT_TRANSACTIONS, and future entities.
-- -----------------------------------------------------------------------------
CREATE SEQUENCE seq_payment_audit START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE payment_audit (
    audit_id        NUMBER(19)     NOT NULL,
    entity_name       VARCHAR2(50)   NOT NULL,
    entity_id           VARCHAR2(30)   NOT NULL,
    action                VARCHAR2(20)   NOT NULL,
    old_value               CLOB,
    new_value                 CLOB,
    performed_by                 VARCHAR2(50)   DEFAULT 'SYSTEM' NOT NULL,
    performed_at                   TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    correlation_id                    VARCHAR2(64),
    CONSTRAINT pk_payment_audit PRIMARY KEY (audit_id),
    CONSTRAINT ck_audit_action CHECK (
        action IN ('INSERT', 'UPDATE', 'DELETE', 'STATUS_CHANGE')
    )
);

CREATE OR REPLACE TRIGGER trg_payment_audit_pk
BEFORE INSERT ON payment_audit
FOR EACH ROW
WHEN (NEW.audit_id IS NULL)
BEGIN
    :NEW.audit_id := seq_payment_audit.NEXTVAL;
END;
/

CREATE INDEX ix_audit_entity ON payment_audit (entity_name, entity_id);
CREATE INDEX ix_audit_correlation ON payment_audit (correlation_id);

COMMENT ON TABLE payment_audit IS 'Enterprise audit trail — every material change to a tracked entity, independent of business status transitions';

-- -----------------------------------------------------------------------------
-- Table: PAYMENT_WEBHOOK_LOG
-- Raw log of every inbound webhook call (mock bank today, real gateway
-- later) — kept even for malformed/rejected payloads, for security review
-- and replay-attack investigation.
-- -----------------------------------------------------------------------------
CREATE SEQUENCE seq_webhook_log START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE payment_webhook_log (
    webhook_log_id         NUMBER(19)     NOT NULL,
    transaction_id           VARCHAR2(30),
    gateway_code               VARCHAR2(30),
    raw_payload                   CLOB           NOT NULL,
    signature_valid                 NUMBER(1)      NOT NULL,
    http_status_returned              NUMBER(3)      NOT NULL,
    received_at                         TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    correlation_id                        VARCHAR2(64),
    CONSTRAINT pk_webhook_log PRIMARY KEY (webhook_log_id),
    CONSTRAINT ck_webhook_sig_valid CHECK (signature_valid IN (0, 1))
    -- Deliberately NO foreign key on transaction_id: a malformed or
    -- replayed webhook may reference a transaction_id that does not exist,
    -- and that row must still be logged for security review, not rejected
    -- at the DB layer.
);

CREATE OR REPLACE TRIGGER trg_webhook_log_pk
BEFORE INSERT ON payment_webhook_log
FOR EACH ROW
WHEN (NEW.webhook_log_id IS NULL)
BEGIN
    :NEW.webhook_log_id := seq_webhook_log.NEXTVAL;
END;
/

CREATE INDEX ix_webhook_txn ON payment_webhook_log (transaction_id);
CREATE INDEX ix_webhook_received ON payment_webhook_log (received_at);

COMMENT ON TABLE payment_webhook_log IS 'Immutable raw log of every inbound webhook call, valid or not — supports replay-attack detection and reconciliation audits';

-- -----------------------------------------------------------------------------
-- Table: SYSTEM_PARAMETERS
-- Generic key/value runtime configuration store — for settings that need
-- to change without a code deploy (e.g. QR TTL, receipt footer text),
-- distinct from the .env-driven ConfigurationManager/PaymentAggregatorConfig
-- which covers deployment-time infrastructure config.
-- -----------------------------------------------------------------------------
CREATE TABLE system_parameters (
    param_key       VARCHAR2(100)  NOT NULL,
    param_value       VARCHAR2(500)  NOT NULL,
    description         VARCHAR2(255),
    is_editable            NUMBER(1)      DEFAULT 1 NOT NULL,
    updated_by                VARCHAR2(50)   DEFAULT 'SYSTEM' NOT NULL,
    updated_date                 TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_system_parameters PRIMARY KEY (param_key),
    CONSTRAINT ck_param_editable CHECK (is_editable IN (0, 1))
);

COMMENT ON TABLE system_parameters IS 'Runtime-editable key/value configuration (QR TTL, receipt footer, etc.) — distinct from deployment-time .env config';

COMMIT;
