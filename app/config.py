"""
Module Name: config.py (business layer)

Purpose:
    Business-specific configuration for the Student Smart Payment Aggregator.

    core.configuration_manager.ApplicationConfig is a closed, frozen
    dataclass that only carries DB/logging/folder settings — it has no
    generic key lookup, and we do not modify it. Instead this module reuses
    core.environment_manager.EnvironmentManager directly (a framework
    component) to resolve business-specific keys, keeping the core
    ConfigurationManager untouched and undupli­cated.

Author:
    Harish

Version:
    1.0.0

Configuration Requirements:
    MOCK_BANK_WEBHOOK_SECRET   - shared secret used to sign/verify mock webhooks
    MOCK_UPI_PAYEE_VPA_SUFFIX  - suffix appended to student UPI ids (default: mockbank)
    QR_PAYLOAD_TTL_SECONDS     - how long a generated UPI QR payload is valid
    MOCK_BANK_BASE_URL         - base URL of the local mock bank simulator (health check use)
    QR_SERVICE_BASE_URL        - base URL of the Node.js QR microservice (server.js, project root)
    QR_SERVICE_TIMEOUT_SECONDS - HTTP timeout (seconds) when calling the QR microservice
    QR_SERVICE_ECC_LEVEL       - default QR error-correction level (L|M|Q|H)
    QR_SERVICE_SIZE_PX         - default QR image dimension in pixels
    RECEIPT_FOOTER_TEXT        - free-text footer printed on generated PDF receipts
"""


from __future__ import annotations

from dataclasses import dataclass

from core.environment_manager import EnvironmentManager


@dataclass(frozen=True)
class PaymentAggregatorConfig:
    """Immutable snapshot of business-specific settings."""

    mock_bank_webhook_secret: str
    mock_upi_payee_vpa_suffix: str
    qr_payload_ttl_seconds: int
    mock_bank_base_url: str
    merchant_name: str
    qr_service_base_url: str
    qr_service_timeout_seconds: float
    qr_service_ecc_level: str
    qr_service_size_px: int
    receipt_footer_text: str

    @classmethod
    def load(cls, env_manager: EnvironmentManager) -> "PaymentAggregatorConfig":
        """
        Build the config from the process environment via EnvironmentManager.

        Args:
            env_manager: The same EnvironmentManager instance already used
                         by ConfigurationManager (or a fresh one — it reads
                         from process env either way, since load_if_exists()
                         has already populated os.environ at bootstrap time).

        Returns:
            A fully resolved PaymentAggregatorConfig.
        """
        return cls(
            mock_bank_webhook_secret=env_manager.get_required(
                "MOCK_BANK_WEBHOOK_SECRET"
            ),
            mock_upi_payee_vpa_suffix=env_manager.get(
                "MOCK_UPI_PAYEE_VPA_SUFFIX", "mockbank"
            ),
            qr_payload_ttl_seconds=int(
                env_manager.get("QR_PAYLOAD_TTL_SECONDS", "900")
            ),
            mock_bank_base_url=env_manager.get(
                "MOCK_BANK_BASE_URL", "http://127.0.0.1:8000"
            ),
            merchant_name=env_manager.get(
                "MERCHANT_NAME", "Demo University"
            ),
            qr_service_base_url=env_manager.get(
                "QR_SERVICE_BASE_URL", "http://127.0.0.1:4000"
            ),
            qr_service_timeout_seconds=float(
                env_manager.get("QR_SERVICE_TIMEOUT_SECONDS", "5")
            ),
            qr_service_ecc_level=env_manager.get("QR_SERVICE_ECC_LEVEL", "M"),
            qr_service_size_px=int(env_manager.get("QR_SERVICE_SIZE_PX", "300")),
            receipt_footer_text=env_manager.get(
                "RECEIPT_FOOTER_TEXT",
                "This is a system-generated receipt and does not require a physical signature.",
            ),
        )
