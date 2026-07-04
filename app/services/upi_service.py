"""
Module Name: upi_service.py

Purpose:
    Builds standard `upi://pay` deep-link strings that any UPI-QR renderer
    (client-side JS library, etc.) can turn into a scannable QR code.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from app.config import PaymentAggregatorConfig


class UpiService:
    def __init__(self, business_config: PaymentAggregatorConfig) -> None:
        self._config = business_config

    def build_upi_uri(
        self,
        payee_vpa: str,
        payee_name: str,
        amount: Decimal,
        transaction_ref: str,
        note: str = "Fee Payment",
    ) -> str:
        """
        Build a standard UPI deep link, e.g.:
        upi://pay?pa=stu1001@mockbank&pn=Aditi%20Sharma&am=45000.00&cu=INR&tr=TXN123&tn=Fee%20Payment

        Args:
            payee_vpa:       The student's assigned static UPI VPA (this is
                              a fee-collection use case, so the "payee" the
                              QR resolves to is the student's own virtual
                              collection account, per your original schema).
            payee_name:      Display name shown in the paying app.
            amount:           Amount to collect.
            transaction_ref:  Our internal transaction_id, passed as `tr` so
                              the (mock) bank webhook can echo it back.
            note:             Free-text note shown to the payer.

        Returns:
            A `upi://pay?...` URI string.
        """
        params = {
            "pa": payee_vpa,
            "pn": payee_name,
            "am": f"{amount:.2f}",
            "cu": "INR",
            "tr": transaction_ref,
            "tn": note,
        }
        query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        return f"upi://pay?{query}"
