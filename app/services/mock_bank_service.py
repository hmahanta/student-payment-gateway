"""
Module Name: mock_bank_service.py

Purpose:
    Simulates the parts of a real bank's webhook contract needed to test
    payment reconciliation completely offline: a shared-secret HMAC
    signature that the "bank" (our own mock endpoint, or the frontend
    'Simulate Payment Success' button) attaches, and that the payment
    service verifies before trusting the callback.

    This is intentionally NOT a real payment gateway integration — it only
    exists so the reconciliation code path can be exercised without any
    external network call, per the offline requirement.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

import hashlib
import hmac
import random
import string

from core.logging_manager import get_logger

from app.config import PaymentAggregatorConfig
from app.exceptions import WebhookSignatureError

log = get_logger(__name__)


class MockBankService:
    def __init__(self, business_config: PaymentAggregatorConfig) -> None:
        self._secret = business_config.mock_bank_webhook_secret

    def sign_payload(self, transaction_id: str, utr: str, status: str) -> str:
        """Compute the HMAC-SHA256 signature the mock bank attaches."""
        message = f"{transaction_id}|{utr}|{status}".encode("utf-8")
        return hmac.new(self._secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_signature(
        self, transaction_id: str, utr: str, status: str, signature: str
    ) -> None:
        """
        Verify a webhook's signature. Raises WebhookSignatureError if it
        does not match — the caller (PaymentService) must not update any
        row unless this passes.
        """
        expected = self.sign_payload(transaction_id, utr, status)
        if not hmac.compare_digest(expected, signature):
            log.warning(
                "Mock webhook signature mismatch for transaction=%s", transaction_id
            )
            raise WebhookSignatureError(
                details={"transaction_id": transaction_id}
            )

    @staticmethod
    def generate_utr() -> str:
        """Generate a realistic-looking mock UTR number for demo purposes."""
        digits = "".join(random.choices(string.digits, k=12))
        return f"MOCKUTR{digits}"
