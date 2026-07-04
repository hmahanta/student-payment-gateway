"""
Module Name: payment_repository.py

Purpose:
    Data access for PaymentTransaction. Provides both standalone methods
    (own session, own commit) for simple reads/inserts, and *_in_session
    variants that participate in a caller-managed transaction — used by
    PaymentService when a single COMMIT must span both
    payment_transactions and fee_invoices (bank webhook reconciliation).

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.constants import PaymentStatus
from app.models.orm_models import PaymentTransaction

log = get_logger(__name__)


class PaymentRepository:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    # ------------------------------------------------------------------
    # Standalone (own session) — used for simple, single-table operations
    # ------------------------------------------------------------------

    def create(self, transaction: PaymentTransaction) -> PaymentTransaction:
        with self._db.session() as sess:
            sess.add(transaction)
            sess.flush()
            sess.expunge(transaction)
            return transaction

    def get_by_id(self, transaction_id: str) -> Optional[PaymentTransaction]:
        with self._db.session() as sess:
            txn = sess.get(PaymentTransaction, transaction_id)
            if txn:
                sess.expunge(txn)
            return txn

    def get_by_bank_reference(self, bank_reference_no: str) -> Optional[PaymentTransaction]:
        with self._db.session() as sess:
            txn = (
                sess.query(PaymentTransaction)
                .filter(PaymentTransaction.bank_reference_no == bank_reference_no)
                .first()
            )
            if txn:
                sess.expunge(txn)
            return txn

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[PaymentTransaction]:
        """Look up a transaction previously created with this idempotency
        key, so a retried initiate-payment call (double-click, network
        retry) returns the existing transaction instead of duplicating it."""
        with self._db.session() as sess:
            txn = (
                sess.query(PaymentTransaction)
                .filter(PaymentTransaction.idempotency_key == idempotency_key)
                .first()
            )
            if txn:
                sess.expunge(txn)
            return txn

    # ------------------------------------------------------------------
    # Session-scoped — participate in a caller-managed atomic transaction
    # ------------------------------------------------------------------

    def get_for_update_in_session(
        self, sess: Session, transaction_id: str
    ) -> Optional[PaymentTransaction]:
        return sess.get(PaymentTransaction, transaction_id, with_for_update=True)

    def update_status_in_session(
        self,
        sess: Session,
        transaction: PaymentTransaction,
        status: PaymentStatus,
        bank_reference_no: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> PaymentTransaction:
        transaction.payment_status = status.value
        if bank_reference_no:
            transaction.bank_reference_no = bank_reference_no
        if failure_reason:
            transaction.failure_reason = failure_reason
        if status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
            transaction.completed_at = datetime.utcnow()
        sess.flush()
        return transaction
