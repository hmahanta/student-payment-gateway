-- =============================================================================
-- Script Name : 01_create_tables.sql
-- Purpose     : DDL for the Student Smart Payment Aggregator (Oracle XE)
-- Author      : Harish
-- Notes       : Run as the application schema user (not SYSTEM/SYS).
--               Compatible with Oracle Database XE 18c / 21c.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Table 1: STUDENTS
-- Stores student identity plus pre-allocated, unique virtual payment
-- identifiers (virtual account, IFSC, static UPI VPA).
-- -----------------------------------------------------------------------------
CREATE TABLE students (
    student_id              VARCHAR2(20)   NOT NULL,
    student_name            VARCHAR2(150)  NOT NULL,
    email                    VARCHAR2(150),
    phone_number             VARCHAR2(15),
    assigned_virtual_account VARCHAR2(34)   NOT NULL,
    assigned_ifsc             VARCHAR2(11)   NOT NULL,
    assigned_upi_id           VARCHAR2(100)  NOT NULL,
    is_active                 NUMBER(1)      DEFAULT 1 NOT NULL,
    created_at                TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at                TIMESTAMP      DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_students PRIMARY KEY (student_id),
    CONSTRAINT uq_students_vacc UNIQUE (assigned_virtual_account),
    CONSTRAINT uq_students_upi UNIQUE (assigned_upi_id),
    CONSTRAINT ck_students_active CHECK (is_active IN (0, 1))
);

COMMENT ON TABLE students IS 'Student master with pre-allocated virtual payment identifiers';
COMMENT ON COLUMN students.assigned_virtual_account IS 'Unique virtual bank account number for Net Banking / NEFT/RTGS credit-back mapping';
COMMENT ON COLUMN students.assigned_upi_id IS 'Static UPI VPA assigned to this student, e.g. student1234@mockbank';

-- -----------------------------------------------------------------------------
-- Table 2: FEE_INVOICES
-- Tracks outstanding and settled fee invoices per student.
-- -----------------------------------------------------------------------------
CREATE TABLE fee_invoices (
    invoice_id       VARCHAR2(20)    NOT NULL,
    student_id       VARCHAR2(20)    NOT NULL,
    fee_description   VARCHAR2(255)   NOT NULL,
    academic_term      VARCHAR2(30),
    amount_due          NUMBER(12,2)    NOT NULL,
    amount_paid          NUMBER(12,2)    DEFAULT 0 NOT NULL,
    invoice_status        VARCHAR2(20)    DEFAULT 'PENDING' NOT NULL,
    due_date               DATE,
    created_at              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_fee_invoices PRIMARY KEY (invoice_id),
    CONSTRAINT fk_invoices_student FOREIGN KEY (student_id)
        REFERENCES students (student_id),
    CONSTRAINT ck_invoice_status CHECK (
        invoice_status IN ('PENDING', 'PARTIAL', 'PAID', 'CANCELLED')
    ),
    CONSTRAINT ck_invoice_amounts CHECK (amount_due >= 0 AND amount_paid >= 0)
);

COMMENT ON TABLE fee_invoices IS 'Outstanding and settled student fee invoices';

CREATE INDEX ix_invoices_student ON fee_invoices (student_id);
CREATE INDEX ix_invoices_status ON fee_invoices (invoice_status);

-- -----------------------------------------------------------------------------
-- Table 3: PAYMENT_TRANSACTIONS
-- Logs every payment attempt for strict auditing and bank reconciliation.
-- -----------------------------------------------------------------------------
CREATE TABLE payment_transactions (
    transaction_id     VARCHAR2(30)    NOT NULL,
    invoice_id          VARCHAR2(20)    NOT NULL,
    student_id           VARCHAR2(20)    NOT NULL,
    bank_reference_no     VARCHAR2(50),
    amount_paid            NUMBER(12,2)    NOT NULL,
    payment_mode             VARCHAR2(20)    NOT NULL,
    payment_status             VARCHAR2(20)    DEFAULT 'PENDING' NOT NULL,
    upi_payload                  VARCHAR2(500),
    failure_reason                 VARCHAR2(255),
    initiated_at                    TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at                     TIMESTAMP,
    created_at                         TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at                           TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_payment_txn PRIMARY KEY (transaction_id),
    CONSTRAINT fk_txn_invoice FOREIGN KEY (invoice_id)
        REFERENCES fee_invoices (invoice_id),
    CONSTRAINT fk_txn_student FOREIGN KEY (student_id)
        REFERENCES students (student_id),
    CONSTRAINT uq_txn_bank_ref UNIQUE (bank_reference_no),
    CONSTRAINT ck_txn_mode CHECK (
        payment_mode IN ('UPI_QR', 'UPI_ID', 'NET_BANKING')
    ),
    CONSTRAINT ck_txn_status CHECK (
        payment_status IN ('PENDING', 'SUCCESS', 'FAILED')
    ),
    CONSTRAINT ck_txn_amount CHECK (amount_paid > 0)
);

COMMENT ON TABLE payment_transactions IS 'Every payment attempt, including bank webhook UTR reconciliation';
COMMENT ON COLUMN payment_transactions.bank_reference_no IS 'UTR / bank reference number returned by the (mock) bank webhook on success';

CREATE INDEX ix_txn_student ON payment_transactions (student_id);
CREATE INDEX ix_txn_invoice ON payment_transactions (invoice_id);
CREATE INDEX ix_txn_status ON payment_transactions (payment_status);

-- -----------------------------------------------------------------------------
-- Trigger: keep updated_at current on row modification (Oracle has no
-- native ON UPDATE CURRENT_TIMESTAMP like MySQL).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TRIGGER trg_students_upd
BEFORE UPDATE ON students
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_invoices_upd
BEFORE UPDATE ON fee_invoices
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_txn_upd
BEFORE UPDATE ON payment_transactions
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

COMMIT;
