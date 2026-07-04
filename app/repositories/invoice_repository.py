"""
Module Name: invoice_repository.py

Purpose:
    Data access for the FeeInvoice entity, via DatabaseManager.session().

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.constants import InvoiceStatus
from app.models.orm_models import FeeInvoice

log = get_logger(__name__)


class InvoiceRepository:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    def get_by_id(self, invoice_id: str) -> Optional[FeeInvoice]:
        with self._db.session() as sess:
            invoice = sess.get(FeeInvoice, invoice_id)
            if invoice:
                sess.expunge(invoice)
            return invoice

    def list_pending_for_student(self, student_id: str) -> list[FeeInvoice]:
        with self._db.session() as sess:
            invoices = (
                sess.query(FeeInvoice)
                .filter(
                    FeeInvoice.student_id == student_id,
                    FeeInvoice.invoice_status.in_(
                        [InvoiceStatus.PENDING.value, InvoiceStatus.PARTIAL.value]
                    ),
                )
                .order_by(FeeInvoice.due_date)
                .all()
            )
            for inv in invoices:
                sess.expunge(inv)
            return invoices

    def apply_payment_in_session(
        self, sess: Session, invoice_id: str, amount: Decimal
    ) -> FeeInvoice:
        """
        Apply a successful payment amount to an invoice and recompute its
        status, using a Session supplied by the caller (PaymentService).

        This is the atomicity-critical path: it is always called alongside
        PaymentRepository.update_status_in_session() inside a single
        DatabaseManager.session() block so that the transaction status and
        the invoice balance commit together, or roll back together.
        """
        invoice = sess.get(FeeInvoice, invoice_id)
        invoice.amount_paid = (invoice.amount_paid or Decimal("0")) + amount
        if invoice.amount_paid >= invoice.amount_due:
            invoice.invoice_status = InvoiceStatus.PAID.value
        elif invoice.amount_paid > 0:
            invoice.invoice_status = InvoiceStatus.PARTIAL.value
        sess.flush()
        return invoice
