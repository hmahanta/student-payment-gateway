"""
Module Name: qr_service_client.py

Purpose:
    Thin HTTP client for the Node.js QR microservice (server.js, project root). This is
    the ONLY place in the Python codebase that knows the QR microservice's
    HTTP contract — PaymentService and the API layer depend on this class,
    never on `httpx` or the microservice's URL directly.

    Per the platform's microservice architecture, Python does not generate
    QR codes itself; it delegates to this Node.js service so the QR
    rendering technology (today: the `qrcode` npm package) can be swapped
    without touching business code.

    Failures are non-fatal to the payment flow by design: if the QR
    microservice is down, `generate_qr()` raises QrServiceUnavailableError,
    which PaymentService catches and degrades gracefully (the transaction
    still gets its `upi://pay` URI; only the pre-rendered image is missing).

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import httpx

from core.logging_manager import get_logger

from app.config import PaymentAggregatorConfig
from app.exceptions import QrServiceUnavailableError

log = get_logger(__name__)


@dataclass(frozen=True)
class QrGenerationResult:
    """Everything the frontend needs to render and countdown a dynamic QR."""

    upi_uri: str
    qr_png_data_url: str
    qr_base64: str
    qr_svg: str
    expires_at: str
    cached: bool


class QrServiceClient:
    def __init__(self, business_config: PaymentAggregatorConfig) -> None:
        self._base_url = business_config.qr_service_base_url.rstrip("/")
        self._timeout = business_config.qr_service_timeout_seconds
        self._default_ecc = business_config.qr_service_ecc_level
        self._default_size_px = business_config.qr_service_size_px

    def generate_qr(
        self,
        student_name: str,
        amount: Decimal,
        upi_id: str,
        transaction_ref: str,
        purpose: str,
        *,
        size_px: Optional[int] = None,
        ecc_level: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        logo_data_url: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> QrGenerationResult:
        """
        Call POST /api/qr/generate on the Node.js microservice.

        Raises:
            QrServiceUnavailableError: on any network error, timeout, or
                non-2xx response — callers decide whether that's fatal.
        """
        correlation_id = correlation_id or uuid.uuid4().hex
        body = {
            "studentName": student_name,
            "amount": float(amount),
            "upiId": upi_id,
            "transactionRef": transaction_ref,
            "purpose": purpose,
            "sizePx": size_px or self._default_size_px,
            "eccLevel": ecc_level or self._default_ecc,
        }
        if ttl_seconds is not None:
            body["ttlSeconds"] = ttl_seconds
        if logo_data_url is not None:
            body["logoDataUrl"] = logo_data_url

        try:
            response = httpx.post(
                f"{self._base_url}/api/qr/generate",
                json=body,
                timeout=self._timeout,
                headers={"X-Correlation-Id": correlation_id},
            )
        except httpx.HTTPError as exc:
            log.warning(
                "QR microservice unreachable: transaction_ref=%s error=%s",
                transaction_ref, exc,
            )
            raise QrServiceUnavailableError(details={"reason": str(exc)}) from exc

        if response.status_code != 200:
            log.warning(
                "QR microservice returned %s for transaction_ref=%s: %s",
                response.status_code, transaction_ref, response.text,
            )
            raise QrServiceUnavailableError(
                details={"status_code": response.status_code, "body": response.text}
            )

        data = response.json()
        return QrGenerationResult(
            upi_uri=data["upiUri"],
            qr_png_data_url=data["qrPngDataUrl"],
            qr_base64=data["qrBase64"],
            qr_svg=data["qrSvg"],
            expires_at=data["expiresAt"],
            cached=data.get("cached", False),
        )

    def is_healthy(self) -> bool:
        """Best-effort liveness probe used by the /api/health endpoint."""
        try:
            response = httpx.get(f"{self._base_url}/health", timeout=self._timeout)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
