"""
Module Name: orm_models.py

Purpose:
    SQLAlchemy ORM models mapped to the Oracle XE tables created by
    sql/01_create_tables.sql, sql/03_migrate_add_audit_columns.sql, and
    sql/04_create_enterprise_tables.sql. Used exclusively through
    core.database_manager.DatabaseManager.session() — no repository ever
    opens its own engine or connection.

    Covers both the original 3-table core schema (students, fee_invoices,
    payment_transactions) and the 5 enterprise tables added later
    (payment_gateway_config, payment_status_history, payment_audit,
    payment_webhook_log, system_parameters).

Author:
    Harish

Version:
    2.0.0
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CLOB,
    Column,
    Date,
    ForeignKey,
    Numeric,
    String,
    TIMESTAMP,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"

    student_id = Column(String(20), primary_key=True)
    student_name = Column(String(150), nullable=False)
    email = Column(String(150))
    phone_number = Column(String(15))
    assigned_virtual_account = Column(String(34), nullable=False, unique=True)
    assigned_ifsc = Column(String(11), nullable=False)
    assigned_upi_id = Column(String(100), nullable=False, unique=True)
    is_active = Column(Numeric(1), default=1, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    created_by = Column(String(50), default="SYSTEM", nullable=False)
    updated_by = Column(String(50))
    record_status = Column(String(20), default="ACTIVE", nullable=False)

    invoices = relationship("FeeInvoice", back_populates="student")


class FeeInvoice(Base):
    __tablename__ = "fee_invoices"

    invoice_id = Column(String(20), primary_key=True)
    student_id = Column(String(20), ForeignKey("students.student_id"), nullable=False)
    fee_description = Column(String(255), nullable=False)
    academic_term = Column(String(30))
    amount_due = Column(Numeric(12, 2), nullable=False)
    amount_paid = Column(Numeric(12, 2), default=0, nullable=False)
    invoice_status = Column(String(20), default="PENDING", nullable=False)
    due_date = Column(Date)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    created_by = Column(String(50), default="SYSTEM", nullable=False)
    updated_by = Column(String(50))
    record_status = Column(String(20), default="ACTIVE", nullable=False)

    student = relationship("Student", back_populates="invoices")
    transactions = relationship("PaymentTransaction", back_populates="invoice")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    transaction_id = Column(String(30), primary_key=True)
    invoice_id = Column(String(20), ForeignKey("fee_invoices.invoice_id"), nullable=False)
    student_id = Column(String(20), ForeignKey("students.student_id"), nullable=False)
    bank_reference_no = Column(String(50), unique=True)
    amount_paid = Column(Numeric(12, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False)
    payment_status = Column(String(20), default="PENDING", nullable=False)
    upi_payload = Column(String(500))
    failure_reason = Column(String(255))
    initiated_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    completed_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    created_by = Column(String(50), default="SYSTEM", nullable=False)
    updated_by = Column(String(50))
    record_status = Column(String(20), default="ACTIVE", nullable=False)

    # Enterprise columns added by sql/03_migrate_add_audit_columns.sql
    gateway_code = Column(String(30), ForeignKey("payment_gateway_config.gateway_code"))
    idempotency_key = Column(String(64), unique=True)
    correlation_id = Column(String(64))

    invoice = relationship("FeeInvoice", back_populates="transactions")


# ---------------------------------------------------------------------------
# Enterprise tables (sql/04_create_enterprise_tables.sql)
# ---------------------------------------------------------------------------


class PaymentGatewayConfig(Base):
    """Adapter registry — one row per payment gateway the orchestrator can
    dispatch to. Onboarding a new provider (Razorpay, PhonePe, ...) is a new
    row here plus a new adapter class — never a change to PaymentService."""

    __tablename__ = "payment_gateway_config"

    gateway_code = Column(String(30), primary_key=True)
    gateway_name = Column(String(100), nullable=False)
    adapter_class = Column(String(150), nullable=False)
    is_enabled = Column(Numeric(1), default=1, nullable=False)
    config_json = Column(CLOB)
    created_by = Column(String(50), default="SYSTEM", nullable=False)
    created_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_by = Column(String(50))
    updated_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    record_status = Column(String(20), default="ACTIVE", nullable=False)


class PaymentStatusHistory(Base):
    """Every status transition a transaction goes through — powers the
    frontend Transaction Timeline view."""

    __tablename__ = "payment_status_history"

    history_id = Column(Numeric(19), primary_key=True)
    transaction_id = Column(
        String(30), ForeignKey("payment_transactions.transaction_id"), nullable=False
    )
    old_status = Column(String(20))
    new_status = Column(String(20), nullable=False)
    changed_by = Column(String(50), default="SYSTEM", nullable=False)
    changed_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    remarks = Column(String(255))
    correlation_id = Column(String(64))


class PaymentAudit(Base):
    """General-purpose entity audit trail (insert/update/field-level
    changes) across STUDENTS, FEE_INVOICES, PAYMENT_TRANSACTIONS."""

    __tablename__ = "payment_audit"

    audit_id = Column(Numeric(19), primary_key=True)
    entity_name = Column(String(50), nullable=False)
    entity_id = Column(String(30), nullable=False)
    action = Column(String(20), nullable=False)
    old_value = Column(CLOB)
    new_value = Column(CLOB)
    performed_by = Column(String(50), default="SYSTEM", nullable=False)
    performed_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    correlation_id = Column(String(64))


class PaymentWebhookLog(Base):
    """Immutable raw log of every inbound webhook call, valid or not —
    supports replay-attack detection and reconciliation audits.

    Deliberately has NO foreign key on transaction_id: a malformed or
    replayed webhook may reference a transaction_id that does not exist,
    and that row must still be logged, not rejected at the DB layer.
    """

    __tablename__ = "payment_webhook_log"

    webhook_log_id = Column(Numeric(19), primary_key=True)
    transaction_id = Column(String(30))
    gateway_code = Column(String(30))
    raw_payload = Column(CLOB, nullable=False)
    signature_valid = Column(Numeric(1), nullable=False)
    http_status_returned = Column(Numeric(3), nullable=False)
    received_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    correlation_id = Column(String(64))


class SystemParameter(Base):
    """Generic key/value runtime configuration store — settings that need
    to change without a code deploy (QR TTL, receipt footer, etc.)."""

    __tablename__ = "system_parameters"

    param_key = Column(String(100), primary_key=True)
    param_value = Column(String(500), nullable=False)
    description = Column(String(255))
    is_editable = Column(Numeric(1), default=1, nullable=False)
    updated_by = Column(String(50), default="SYSTEM", nullable=False)
    updated_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
