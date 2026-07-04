"""
Module Name: reports_service.py

Purpose:
    Business-facing reporting API: Daily Collection, Pending Fees,
    Collected Fees, Failed Payments, Student Ledger, Payment Register,
    Reconciliation Report, Audit Report, and Webhook Report — the
    "Reports" and "Dashboard" functional modules from the platform spec.

    This service composes ReportsRepository (transactional data) with
    AuditService (audit trail / webhook log) so a single call gives the
    frontend everything it needs for each report tab.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from typing import Any

from core.logging_manager import get_logger

from app.repositories.reports_repository import ReportsRepository
from app.services.audit_service import AuditService

log = get_logger(__name__)


class ReportsService:
    def __init__(self, reports_repository: ReportsRepository, audit_service: AuditService) -> None:
        self._repo = reports_repository
        self._audit = audit_service

    def dashboard_summary(self) -> dict[str, Any]:
        return self._repo.dashboard_summary()

    def daily_collection(self, days: int = 30) -> list[dict[str, Any]]:
        return self._repo.daily_collection(days=days)

    def pending_fees(self) -> list[dict[str, Any]]:
        return self._repo.pending_fees()

    def collected_fees(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._repo.collected_fees(limit=limit)

    def failed_payments(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._repo.failed_payments(limit=limit)

    def payment_register(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._repo.payment_register(limit=limit)

    def student_ledger(self, student_id: str) -> list[dict[str, Any]]:
        return self._repo.student_ledger(student_id)

    def audit_report(self, entity_name: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        return self._audit.get_audit_trail(entity_name=entity_name, entity_id=entity_id)

    def webhook_report(self) -> list[dict[str, Any]]:
        return self._audit.get_webhook_log()

    def reconciliation_report(self) -> dict[str, Any]:
        """
        Cross-checks settled (SUCCESS) transactions against inbound webhook
        log entries: every SUCCESS transaction should have at least one
        webhook_log row with signature_valid=1 for the same transaction_id.
        Flags any mismatch as a reconciliation exception for manual review.
        """
        settled = self._repo.collected_fees(limit=2000)
        webhook_rows = self._audit.get_webhook_log(limit=2000)
        valid_webhook_txn_ids = {
            row["transaction_id"] for row in webhook_rows if row["signature_valid"] and row["transaction_id"]
        }

        matched = [t for t in settled if t["transaction_id"] in valid_webhook_txn_ids]
        exceptions = [t for t in settled if t["transaction_id"] not in valid_webhook_txn_ids]

        return {
            "total_settled_transactions": len(settled),
            "matched_with_webhook_log": len(matched),
            "reconciliation_exceptions": exceptions,
        }
