"""
Module Name: bootstrap.py

Purpose:
    Business-layer composition root for the Student Smart Payment
    Aggregator. Bootstraps the existing core.ApplicationContext (unchanged),
    layers on business-specific configuration and folders, and constructs
    the repository/service graph via constructor injection.

    This is the ONLY place object wiring happens. FastAPI route handlers
    never construct services themselves — they depend on the singleton
    built here.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import ClassVar, Optional

from core.application_context import ApplicationContext
from core.configuration_manager import ConfigurationManager
from core.constants import FolderNames
from core.logging_manager import get_logger

from app.config import PaymentAggregatorConfig
from app.constants import BusinessFolderNames
from app.repositories.student_repository import StudentRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.payment_repository import PaymentRepository
from app.services.upi_service import UpiService
from app.services.mock_bank_service import MockBankService
from app.services.qr_service_client import QrServiceClient
from app.services.receipt_service import ReceiptService
from app.services.student_service import StudentService
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService

log = get_logger(__name__)

# Oracle tables the framework HealthCheckManager should verify at startup.
REQUIRED_TABLES = ("STUDENTS", "FEE_INVOICES", "PAYMENT_TRANSACTIONS")

# Business env keys the framework HealthCheckManager should verify exist.
REQUIRED_BUSINESS_ENV_KEYS = ("MOCK_BANK_WEBHOOK_SECRET",)


@dataclass
class AppServices:
    """
    Fully-wired business service graph for the Payment Aggregator.

    This is the object FastAPI dependencies pull from — a thin, explicit
    alternative to a generic service locator.
    """

    ctx: ApplicationContext
    business_config: PaymentAggregatorConfig
    student_service: StudentService
    invoice_service: InvoiceService
    payment_service: PaymentService
    mock_bank_service: MockBankService
    qr_service_client: QrServiceClient
    receipt_service: ReceiptService


class Bootstrap:
    """Idempotent singleton wiring for the business application."""

    _instance: ClassVar[Optional[AppServices]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_services(cls) -> AppServices:
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is not None:
                return cls._instance
            cls._instance = cls._build()
            return cls._instance

    @classmethod
    def _build(cls) -> AppServices:
        log.info("Bootstrapping Student Smart Payment Aggregator…")

        # 1. Framework bootstrap — unchanged, reused as infrastructure.
        ctx = ApplicationContext.bootstrap(
            env_file=".env",
            init_db=True,
            required_tables=list(REQUIRED_TABLES),
            required_env_keys=list(REQUIRED_BUSINESS_ENV_KEYS),
            run_health_checks=True,
        )

        # 2. Business-specific folders, registered additively via the
        #    existing FolderManager — core.folder_manager is not modified.
        ctx.folders.create_folder(
            BusinessFolderNames.QR_CODES.value,
            relative_path=f"{FolderNames.OUTPUT.value}/{BusinessFolderNames.QR_CODES.value}",
        )
        ctx.folders.create_folder(
            BusinessFolderNames.RECEIPTS.value,
            relative_path=f"{FolderNames.OUTPUT.value}/{BusinessFolderNames.RECEIPTS.value}",
        )

        # 3. Business-specific configuration, resolved via the framework's
        #    EnvironmentManager (reused, not duplicated).
        cfg_manager = ConfigurationManager.get_instance()
        business_config = PaymentAggregatorConfig.load(cfg_manager._env_manager)  # noqa: SLF001

        # 4. Repositories — all DB access goes through ctx.db.
        student_repo = StudentRepository(ctx.db)
        invoice_repo = InvoiceRepository(ctx.db)
        payment_repo = PaymentRepository(ctx.db)

        # 5. Domain services — future managers (cache/audit/notification/
        #    metrics) are optional constructor params, currently None,
        #    to be supplied here without touching service internals once
        #    the framework provides them.
        upi_service = UpiService(business_config)
        mock_bank_service = MockBankService(business_config)
        qr_service_client = QrServiceClient(business_config)

        student_service = StudentService(student_repo)
        invoice_service = InvoiceService(invoice_repo)
        payment_service = PaymentService(
            payment_repository=payment_repo,
            invoice_repository=invoice_repo,
            student_repository=student_repo,
            upi_service=upi_service,
            mock_bank_service=mock_bank_service,
            db_manager=ctx.db,
            qr_service_client=qr_service_client,
        )
        receipt_service = ReceiptService(
            payment_repository=payment_repo,
            invoice_repository=invoice_repo,
            student_repository=student_repo,
            business_config=business_config,
            output_dir=ctx.folders.get(BusinessFolderNames.RECEIPTS.value),
        )

        log.info("Bootstrap complete — services ready.")
        return AppServices(
            ctx=ctx,
            business_config=business_config,
            student_service=student_service,
            invoice_service=invoice_service,
            payment_service=payment_service,
            mock_bank_service=mock_bank_service,
            qr_service_client=qr_service_client,
            receipt_service=receipt_service,
        )

    @classmethod
    def reset(cls) -> None:
        """Test-only: tear down business services and the framework context."""
        with cls._lock:
            cls._instance = None
            ApplicationContext.reset()
