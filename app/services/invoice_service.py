"""
Module Name: invoice_service.py

Purpose:
    Business logic for fee invoice lookups.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from core.logging_manager import get_logger

from app.exceptions import InvoiceNotFoundError
from app.models.orm_models import FeeInvoice
from app.repositories.invoice_repository import InvoiceRepository

log = get_logger(__name__)


class InvoiceService:
    def __init__(
        self,
        invoice_repository: InvoiceRepository,
        cache_manager: object | None = None,
        audit_manager: object | None = None,
    ) -> None:
        self._repo = invoice_repository
        self._cache = cache_manager
        self._audit = audit_manager

    def get_invoice(self, invoice_id: str) -> FeeInvoice:
        invoice = self._repo.get_by_id(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        return invoice

    def get_pending_invoices_for_student(self, student_id: str) -> list[FeeInvoice]:
        return self._repo.list_pending_for_student(student_id)
