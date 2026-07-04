"""
Module Name: exceptions.py (business layer)

Purpose:
    Domain-specific exceptions for the Student Smart Payment Aggregator.
    All exceptions subclass core.exception_manager.ApplicationError so that
    callers can catch at the framework level or the domain level, and every
    exception remains serialisable via .to_dict() exactly like framework
    exceptions.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from typing import Any

from core.exception_manager import ApplicationError


class StudentNotFoundError(ApplicationError):
    def __init__(self, student_id: str, details: Any = None) -> None:
        super().__init__(
            f"Student '{student_id}' was not found.",
            details=details,
            error_code="PAY-404-STU",
        )
        self.student_id = student_id


class InvoiceNotFoundError(ApplicationError):
    def __init__(self, invoice_id: str, details: Any = None) -> None:
        super().__init__(
            f"Invoice '{invoice_id}' was not found.",
            details=details,
            error_code="PAY-404-INV",
        )
        self.invoice_id = invoice_id


class InvoiceAlreadySettledError(ApplicationError):
    def __init__(self, invoice_id: str, details: Any = None) -> None:
        super().__init__(
            f"Invoice '{invoice_id}' is already fully paid.",
            details=details,
            error_code="PAY-409-INV",
        )
        self.invoice_id = invoice_id


class TransactionNotFoundError(ApplicationError):
    def __init__(self, transaction_id: str, details: Any = None) -> None:
        super().__init__(
            f"Transaction '{transaction_id}' was not found.",
            details=details,
            error_code="PAY-404-TXN",
        )
        self.transaction_id = transaction_id


class DuplicateWebhookError(ApplicationError):
    def __init__(self, transaction_id: str, details: Any = None) -> None:
        super().__init__(
            f"Transaction '{transaction_id}' has already been settled; "
            f"duplicate webhook ignored.",
            details=details,
            error_code="PAY-409-DUP",
        )
        self.transaction_id = transaction_id


class WebhookSignatureError(ApplicationError):
    def __init__(self, details: Any = None) -> None:
        super().__init__(
            "Mock bank webhook signature verification failed.",
            details=details,
            error_code="PAY-401-SIG",
        )


class PaymentValidationError(ApplicationError):
    def __init__(self, message: str, field: str | None = None, details: Any = None) -> None:
        super().__init__(message, details=details, error_code="PAY-422-VAL")
        self.field = field


class QrServiceUnavailableError(ApplicationError):
    """
    Raised when the Node.js QR microservice cannot be reached or returns an
    error. Payment initiation itself is NOT blocked by this — PaymentService
    catches it, logs a warning, and falls back to returning the raw
    `upi://pay` URI without a rendered image, so a temporarily-down QR
    microservice never stops fee collection outright.
    """

    def __init__(self, details: Any = None) -> None:
        super().__init__(
            "The QR microservice is unavailable or returned an error.",
            details=details,
            error_code="PAY-503-QR",
        )


class ReceiptNotAvailableError(ApplicationError):
    def __init__(self, transaction_id: str, details: Any = None) -> None:
        super().__init__(
            f"A receipt cannot be generated for transaction '{transaction_id}' "
            f"because it has not been settled with a SUCCESS status.",
            details=details,
            error_code="PAY-409-RCT",
        )
        self.transaction_id = transaction_id
