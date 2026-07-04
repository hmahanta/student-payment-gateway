"""
Module Name: audit_service.py

Purpose:
    Enterprise audit trail for the Payment Aggregator, writing to the three
    audit-oriented tables created by sql/04_create_enterprise_tables.sql:

      - payment_audit           general entity change log (insert/update/
                                 status-change), keyed by (entity_name,
                                 entity_id)
      - payment_status_history  every PENDING -> SUCCESS/FAILED transition
                                 a transaction goes through, powering the
                                 frontend Transaction Timeline view
      - payment_webhook_log     an immutable record of EVERY inbound
                                 webhook call, valid or not, for security
                                 review and replay-attack investigation

    All writes here are best-effort: a failure to write an audit row must
    never fail the business operation it is describing. Methods therefore
    swallow and log any exception rather than propagating it, unless a
    caller-supplied Session is passed in (session-scoped calls participate
    in the caller's transaction and rely on the caller's rollback/commit).

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from core.database_manager import DatabaseManager
from core.logging_manager import get_logger

from app.models.orm_models import PaymentAudit, PaymentStatusHistory, PaymentWebhookLog

log = get_logger(__name__)


class AuditService:
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    # ------------------------------------------------------------------
    # Standalone (own session) — safe to call from anywhere, never raises
    # ------------------------------------------------------------------

    def record_audit(
        self,
        entity_name: str,
        entity_id: str,
        action: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        performed_by: str = "SYSTEM",
        correlation_id: Optional[str] = None,
    ) -> None:
        """Insert a general-purpose audit row. Never raises."""
        try:
            with self._db.session() as sess:
                sess.add(
                    PaymentAudit(
                        entity_name=entity_name,
                        entity_id=entity_id,
                        action=action,
                        old_value=old_value,
                        new_value=new_value,
                        performed_by=performed_by,
                        correlation_id=correlation_id,
                    )
                )
        except Exception:  # noqa: BLE001 — audit logging must never break the caller
            log.exception(
                "Failed to write payment_audit row: entity=%s/%s action=%s",
                entity_name, entity_id, action,
            )

    def log_webhook(
        self,
        transaction_id: Optional[str],
        raw_payload: str,
        signature_valid: bool,
        http_status_returned: int,
        gateway_code: str = "MOCK_BANK",
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Log an inbound webhook call, valid or not. Deliberately never
        raises and never blocks reconciliation — this is a forensic log,
        not a gatekeeper.
        """
        try:
            with self._db.session() as sess:
                sess.add(
                    PaymentWebhookLog(
                        transaction_id=transaction_id,
                        gateway_code=gateway_code,
                        raw_payload=raw_payload,
                        signature_valid=1 if signature_valid else 0,
                        http_status_returned=http_status_returned,
                        correlation_id=correlation_id,
                    )
                )
        except Exception:  # noqa: BLE001
            log.exception(
                "Failed to write payment_webhook_log row: transaction=%s",
                transaction_id,
            )

    # ------------------------------------------------------------------
    # Session-scoped — participate in a caller-managed atomic transaction
    # ------------------------------------------------------------------

    def record_status_change_in_session(
        self,
        sess: Session,
        transaction_id: str,
        old_status: Optional[str],
        new_status: str,
        changed_by: str = "SYSTEM",
        remarks: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Insert a payment_status_history row as PART OF the caller's
        transaction (same session as the transaction/invoice update), so
        the timeline entry commits or rolls back atomically with the
        business change it describes.
        """
        sess.add(
            PaymentStatusHistory(
                transaction_id=transaction_id,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                remarks=remarks,
                correlation_id=correlation_id,
            )
        )

    def get_status_history(self, transaction_id: str) -> list[dict[str, Any]]:
        """Fetch the full transition timeline for a transaction, oldest first."""
        with self._db.session() as sess:
            rows = (
                sess.query(PaymentStatusHistory)
                .filter(PaymentStatusHistory.transaction_id == transaction_id)
                .order_by(PaymentStatusHistory.changed_at)
                .all()
            )
            return [
                {
                    "old_status": r.old_status,
                    "new_status": r.new_status,
                    "changed_by": r.changed_by,
                    "changed_at": r.changed_at.isoformat() if r.changed_at else None,
                    "remarks": r.remarks,
                }
                for r in rows
            ]

    def get_audit_trail(
        self, entity_name: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Fetch recent audit rows, optionally filtered by entity."""
        with self._db.session() as sess:
            query = sess.query(PaymentAudit)
            if entity_name:
                query = query.filter(PaymentAudit.entity_name == entity_name)
            if entity_id:
                query = query.filter(PaymentAudit.entity_id == entity_id)
            rows = query.order_by(PaymentAudit.performed_at.desc()).limit(limit).all()
            return [
                {
                    "entity_name": r.entity_name,
                    "entity_id": r.entity_id,
                    "action": r.action,
                    "performed_by": r.performed_by,
                    "performed_at": r.performed_at.isoformat() if r.performed_at else None,
                    "correlation_id": r.correlation_id,
                }
                for r in rows
            ]

    def get_webhook_log(self, limit: int = 200) -> list[dict[str, Any]]:
        """Fetch recent webhook log rows, most recent first."""
        with self._db.session() as sess:
            rows = (
                sess.query(PaymentWebhookLog)
                .order_by(PaymentWebhookLog.received_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "transaction_id": r.transaction_id,
                    "gateway_code": r.gateway_code,
                    "signature_valid": bool(r.signature_valid),
                    "http_status_returned": r.http_status_returned,
                    "received_at": r.received_at.isoformat() if r.received_at else None,
                    "correlation_id": r.correlation_id,
                }
                for r in rows
            ]
