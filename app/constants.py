"""
Module Name: constants.py (business layer)

Purpose:
    Business-specific enums and constants for the Student Smart Payment
    Aggregator. Does NOT duplicate core.constants — extends it with
    domain vocabulary that the framework has no knowledge of.

Author:
    Harish

Version:
    1.0.0
"""

from enum import Enum


class PaymentMode(str, Enum):
    UPI_QR = "UPI_QR"
    UPI_ID = "UPI_ID"
    NET_BANKING = "NET_BANKING"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


# Business folder names registered at startup via
# core.folder_manager.FolderManager.create_folder() — additive, framework
# untouched.
class BusinessFolderNames(str, Enum):
    QR_CODES = "qr_codes"
    RECEIPTS = "receipts"
