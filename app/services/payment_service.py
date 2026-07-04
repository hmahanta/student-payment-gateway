"""
Module Name: payment_service.py

Purpose:
    Core business logic for the Payment Aggregator:
      1. Initiate a payment (creates a PENDING transaction row, and for
         UPI modes generates the `upi://pay` deep link string).
      2. Reconcile a (mock) bank webhook: verifies the signature, then
         atomically updates payment_transactions.payment_status and
         fee_invoices.amount_paid/invoice_status in a single COMMIT.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.constants import PaymentMode, PaymentStatus
from app.exceptions import (
    DuplicateWebhookError,
    InvoiceAlreadySettledError,
    InvoiceNotFoundError,
    PaymentValidationError,
    QrServiceUnavailableError,
    StudentNotFoundError,
    TransactionNotFoundError,
)
from app.models.orm_models import PaymentTransaction
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.student_repository import StudentRepository
from app.services.mock_bank_service import MockBankService
from app.services.qr_service_client import QrServiceClient
from app.services.upi_service import UpiService

log = get_logger(__name__)


class PaymentService:
    def __init__(
        self,
        payment_repository: PaymentRepository,
        invoice_repository: InvoiceRepository,
        student_repository: StudentRepository,
        upi_service: UpiService,
        mock_bank_service: MockBankService,
        db_manager: DatabaseManager,
        qr_service_client: QrServiceClient | None = None,
        # future managers — optional, default None until framework provides them
        cache_manager: object | None = None,
        audit_manager: object | None = None,
        notification_manager: object | None = None,
        metrics_manager: object | None = None,
    ) -> None:
        self._payment_repo = payment_repository
        self._invoice_repo = invoice_repository
        self._student_repo = student_repository
        self._upi_service = upi_service
        self._mock_bank = mock_bank_service
        self._db = db_manager
        self._qr_service = qr_service_client
        self._cache = cache_manager
        self._audit = audit_manager
        self._notification = notification_manager
        self._metrics = metrics_manager

    # ------------------------------------------------------------------
    # 1. Payment initiation
    # ------------------------------------------------------------------

    def initiate_payment(
        self, student_id: str, invoice_id: str, payment_mode: PaymentMode
    ) -> dict:
        """
        Create a PENDING transaction row. For UPI_QR / UPI_ID, also returns
        the `upi://pay` string for the frontend to render as a QR code.

        Returns:
            dict with transaction_id, payment_status, amount, payment_mode,
            and upi_uri (None for NET_BANKING).
        """
        student = self._student_repo.get_by_id(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)

        invoice = self._invoice_repo.get_by_id(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        if invoice.invoice_status == "PAID":
            raise InvoiceAlreadySettledError(invoice_id)

        outstanding = Decimal(invoice.amount_due) - Decimal(invoice.amount_paid or 0)
        if outstanding <= 0:
            raise InvoiceAlreadySettledError(invoice_id)

        transaction_id = f"TXN{uuid.uuid4().hex[:16].upper()}"

        upi_uri = None
        qr_image: dict | None = None
        if payment_mode in (PaymentMode.UPI_QR, PaymentMode.UPI_ID):
            upi_uri = self._upi_service.build_upi_uri(
                payee_vpa=student.assigned_upi_id,
                payee_name=student.student_name,
                amount=outstanding,
                transaction_ref=transaction_id,
                note=f"Fee payment for {invoice.fee_description}",
            )

            # Only UPI_QR needs a rendered image; UPI_ID just shows the VPA
            # for the payer to enter manually in their own UPI app.
            if payment_mode == PaymentMode.UPI_QR and self._qr_service is not None:
                try:
                    qr_result = self._qr_service.generate_qr(
                        student_name=student.student_name,
                        amount=outstanding,
                        upi_id=student.assigned_upi_id,
                        transaction_ref=transaction_id,
                        purpose=f"Fee payment for {invoice.fee_description}",
                        correlation_id=transaction_id,
                    )
                    qr_image = {
                        "qr_png_data_url": qr_result.qr_png_data_url,
                        "qr_svg": qr_result.qr_svg,
                        "expires_at": qr_result.expires_at,
                    }
                except QrServiceUnavailableError as exc:
                    # Non-fatal: the transaction still proceeds with the raw
                    # upi_uri. The frontend can render *something* scannable
                    # itself, or the operator can read the VPA aloud — a
                    # temporarily-down QR microservice must never block fee
                    # collection.
                    log.warning(
                        "QR image generation unavailable for transaction=%s: %s",
                        transaction_id, exc,
                    )

        transaction = PaymentTransaction(
            transaction_id=transaction_id,
            invoice_id=invoice_id,
            student_id=student_id,
            amount_paid=outstanding,
            payment_mode=payment_mode.value,
            payment_status=PaymentStatus.PENDING.value,
            upi_payload=upi_uri,
        )
        self._payment_repo.create(transaction)

        log.info(
            "Payment initiated: transaction=%s student=%s invoice=%s mode=%s amount=%s",
            transaction_id, student_id, invoice_id, payment_mode.value, outstanding,
        )

        return {
            "transaction_id": transaction_id,
            "payment_status": PaymentStatus.PENDING.value,
            "amount": float(outstanding),
            "payment_mode": payment_mode.value,
            "upi_uri": upi_uri,
            "virtual_account": student.assigned_virtual_account,
            "ifsc": student.assigned_ifsc,
            "qr_png_data_url": qr_image["qr_png_data_url"] if qr_image else None,
            "qr_svg": qr_image["qr_svg"] if qr_image else None,
            "qr_expires_at": qr_image["expires_at"] if qr_image else None,
        }

    # ------------------------------------------------------------------
    # 2. Mock bank webhook reconciliation (atomic)
    # ------------------------------------------------------------------

    def reconcile_webhook(
        self,
        transaction_id: str,
        bank_reference_no: str,
        status: str,
        signature: str,
    ) -> dict:
        """
        Verify the mock bank webhook signature, then atomically update the
        transaction and the invoice balance in a single DatabaseManager
        session (one COMMIT, or a full rollback on any failure).

        Args:
            transaction_id:     Our internal transaction id.
            bank_reference_no:  The UTR the mock bank generated.
            status:             "SUCCESS" or "FAILED".
            signature:          HMAC signature to verify against our secret.

        Returns:
            dict summary of the final transaction + invoice state.
        """
        if status not in (PaymentStatus.SUCCESS.value, PaymentStatus.FAILED.value):
            raise PaymentValidationError(
                f"Unsupported webhook status '{status}'.", field="status"
            )

        # Signature must be verified BEFORE any DB row is touched.
        self._mock_bank.verify_signature(
            transaction_id, bank_reference_no, status, signature
        )

        # NOTE: DatabaseManager.session() wraps ANY exception raised inside
        # its `with` block into DatabaseQueryError (by design — it can't
        # tell a domain 404/409 apart from a real SQL failure). So domain
        # exceptions are captured here and re-raised AFTER the block exits,
        # never inside it, to preserve their original type/HTTP mapping.
        pending_error: Exception | None = None
        result: dict | None = None

        with self._db.session() as sess:
            transaction = self._payment_repo.get_for_update_in_session(
                sess, transaction_id
            )
            if transaction is None:
                pending_error = TransactionNotFoundError(transaction_id)
            elif transaction.payment_status != PaymentStatus.PENDING.value:
                pending_error = DuplicateWebhookError(transaction_id)
            else:
                new_status = PaymentStatus(status)
                self._payment_repo.update_status_in_session(
                    sess,
                    transaction,
                    new_status,
                    bank_reference_no=bank_reference_no,
                    failure_reason=None if new_status == PaymentStatus.SUCCESS else "Mock bank reported failure",
                )

                invoice_summary = None
                if new_status == PaymentStatus.SUCCESS:
                    invoice = self._invoice_repo.apply_payment_in_session(
                        sess, transaction.invoice_id, Decimal(transaction.amount_paid)
                    )
                    invoice_summary = {
                        "invoice_id": invoice.invoice_id,
                        "invoice_status": invoice.invoice_status,
                        "amount_paid": float(invoice.amount_paid),
                        "amount_due": float(invoice.amount_due),
                    }
                # sess commits automatically on context-manager exit (DatabaseManager.session())

                result = {
                    "transaction_id": transaction.transaction_id,
                    "payment_status": transaction.payment_status,
                    "bank_reference_no": transaction.bank_reference_no,
                    "invoice": invoice_summary,
                }

        if pending_error is not None:
            log.warning(
                "Webhook reconciliation rejected: transaction=%s reason=%s",
                transaction_id, pending_error,
            )
            raise pending_error

        log.info(
            "Webhook reconciled: transaction=%s status=%s utr=%s",
            transaction_id, status, bank_reference_no,
        )
        return result

    def get_transaction(self, transaction_id: str) -> PaymentTransaction:
        transaction = self._payment_repo.get_by_id(transaction_id)
        if transaction is None:
            raise TransactionNotFoundError(transaction_id)
        return transaction
