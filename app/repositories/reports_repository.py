"""
Module Name: reports_repository.py

Purpose:
    Read-only aggregate/reporting queries backing the Reports module:
    Daily Collection, Pending Fees, Collected Fees, Failed Payments,
    Student Ledger, and Payment Register. Every query runs through
    DatabaseManager.session() like every other repository — no separate
    reporting connection or warehouse, by design (single local Oracle XE
    instance, per the offline requirement).

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import func

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.models.orm_models import FeeInvoice, PaymentTransaction, Student

log = get_logger(__name__)


class ReportsRepository:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def daily_collection(self, days: int = 30) -> list[dict[str, Any]]:
        """SUCCESS amount collected, grouped by settlement date, most recent first."""
        with self._db.session() as sess:
            day_col = func.trunc(PaymentTransaction.completed_at)
            rows = (
                sess.query(
                    day_col.label("collection_date"),
                    func.count(PaymentTransaction.transaction_id).label("txn_count"),
                    func.sum(PaymentTransaction.amount_paid).label("total_amount"),
                )
                .filter(PaymentTransaction.payment_status == "SUCCESS")
                .group_by(day_col)
                .order_by(day_col.desc())
                .limit(days)
                .all()
            )
            return [
                {
                    "collection_date": str(r.collection_date),
                    "transaction_count": r.txn_count,
                    "total_amount": float(r.total_amount or 0),
                }
                for r in rows
            ]

    def pending_fees(self) -> list[dict[str, Any]]:
        with self._db.session() as sess:
            rows = (
                sess.query(FeeInvoice, Student.student_name)
                .join(Student, Student.student_id == FeeInvoice.student_id)
                .filter(FeeInvoice.invoice_status.in_(["PENDING", "PARTIAL"]))
                .order_by(FeeInvoice.due_date)
                .all()
            )
            return [
                {
                    "invoice_id": inv.invoice_id,
                    "student_id": inv.student_id,
                    "student_name": name,
                    "fee_description": inv.fee_description,
                    "amount_due": float(inv.amount_due),
                    "amount_paid": float(inv.amount_paid),
                    "outstanding": float(inv.amount_due - inv.amount_paid),
                    "invoice_status": inv.invoice_status,
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                }
                for inv, name in rows
            ]

    def collected_fees(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._db.session() as sess:
            rows = (
                sess.query(PaymentTransaction, Student.student_name)
                .join(Student, Student.student_id == PaymentTransaction.student_id)
                .filter(PaymentTransaction.payment_status == "SUCCESS")
                .order_by(PaymentTransaction.completed_at.desc())
                .limit(limit)
                .all()
            )
            return [self._txn_row(t, name) for t, name in rows]

    def failed_payments(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._db.session() as sess:
            rows = (
                sess.query(PaymentTransaction, Student.student_name)
                .join(Student, Student.student_id == PaymentTransaction.student_id)
                .filter(PaymentTransaction.payment_status == "FAILED")
                .order_by(PaymentTransaction.completed_at.desc())
                .limit(limit)
                .all()
            )
            return [self._txn_row(t, name) for t, name in rows]

    def payment_register(self, limit: int = 500) -> list[dict[str, Any]]:
        """Full chronological register of every transaction attempt, any status."""
        with self._db.session() as sess:
            rows = (
                sess.query(PaymentTransaction, Student.student_name)
                .join(Student, Student.student_id == PaymentTransaction.student_id)
                .order_by(PaymentTransaction.initiated_at.desc())
                .limit(limit)
                .all()
            )
            return [self._txn_row(t, name) for t, name in rows]

    def student_ledger(self, student_id: str) -> list[dict[str, Any]]:
        with self._db.session() as sess:
            rows = (
                sess.query(FeeInvoice)
                .filter(FeeInvoice.student_id == student_id)
                .order_by(FeeInvoice.created_at)
                .all()
            )
            return [
                {
                    "invoice_id": inv.invoice_id,
                    "fee_description": inv.fee_description,
                    "academic_term": inv.academic_term,
                    "amount_due": float(inv.amount_due),
                    "amount_paid": float(inv.amount_paid),
                    "invoice_status": inv.invoice_status,
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                }
                for inv in rows
            ]

    def dashboard_summary(self) -> dict[str, Any]:
        with self._db.session() as sess:
            total_students = sess.query(func.count(Student.student_id)).filter(
                Student.is_active == 1
            ).scalar() or 0

            pending_count, pending_amount = sess.query(
                func.count(FeeInvoice.invoice_id),
                func.coalesce(func.sum(FeeInvoice.amount_due - FeeInvoice.amount_paid), 0),
            ).filter(FeeInvoice.invoice_status.in_(["PENDING", "PARTIAL"])).one()

            # NOTE: deliberately compares against a Python-computed date
            # (bound as a literal) rather than an Oracle SYSDATE()-style
            # call — SQLAlchemy's generic func.sysdate() renders with
            # parentheses, which is invalid Oracle syntax for the
            # no-argument SYSDATE keyword.
            today = date.today()
            collected_today = sess.query(
                func.coalesce(func.sum(PaymentTransaction.amount_paid), 0)
            ).filter(
                PaymentTransaction.payment_status == "SUCCESS",
                func.trunc(PaymentTransaction.completed_at) == today,
            ).scalar() or 0

            success_count = sess.query(func.count(PaymentTransaction.transaction_id)).filter(
                PaymentTransaction.payment_status == "SUCCESS"
            ).scalar() or 0

            failed_count = sess.query(func.count(PaymentTransaction.transaction_id)).filter(
                PaymentTransaction.payment_status == "FAILED"
            ).scalar() or 0

            pending_txn_count = sess.query(func.count(PaymentTransaction.transaction_id)).filter(
                PaymentTransaction.payment_status == "PENDING"
            ).scalar() or 0

            return {
                "total_active_students": int(total_students),
                "pending_invoice_count": int(pending_count or 0),
                "total_outstanding_amount": float(pending_amount or 0),
                "collected_today": float(collected_today or 0),
                "successful_transactions": int(success_count),
                "failed_transactions": int(failed_count),
                "pending_transactions": int(pending_txn_count),
            }

    @staticmethod
    def _txn_row(t: PaymentTransaction, student_name: str) -> dict[str, Any]:
        return {
            "transaction_id": t.transaction_id,
            "student_id": t.student_id,
            "student_name": student_name,
            "invoice_id": t.invoice_id,
            "amount_paid": float(t.amount_paid),
            "payment_mode": t.payment_mode,
            "payment_status": t.payment_status,
            "bank_reference_no": t.bank_reference_no,
            "failure_reason": t.failure_reason,
            "initiated_at": t.initiated_at.isoformat() if t.initiated_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
