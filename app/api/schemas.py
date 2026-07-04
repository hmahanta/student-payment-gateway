"""
Module Name: schemas.py

Purpose:
    Pydantic v2 request/response models for the Payment Aggregator REST API.

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class StudentOut(BaseModel):
    student_id: str
    student_name: str
    assigned_virtual_account: str
    assigned_ifsc: str
    assigned_upi_id: str


class InvoiceOut(BaseModel):
    invoice_id: str
    fee_description: str
    amount_due: float
    amount_paid: float
    invoice_status: str
    due_date: Optional[date] = None


class StudentProfileResponse(BaseModel):
    student: StudentOut
    pending_invoices: list[InvoiceOut]


class InitiatePaymentRequest(BaseModel):
    student_id: str = Field(..., examples=["STU1001"])
    invoice_id: str = Field(..., examples=["INV2001"])
    payment_mode: str = Field(..., examples=["UPI_QR", "UPI_ID", "NET_BANKING"])


class InitiatePaymentResponse(BaseModel):
    transaction_id: str
    payment_status: str
    amount: float
    payment_mode: str
    upi_uri: Optional[str] = None
    virtual_account: str
    ifsc: str
    qr_png_data_url: Optional[str] = Field(
        default=None,
        description="Base64 data-URL PNG of the QR, rendered by the Node.js "
                    "QR microservice. None if payment_mode != UPI_QR or the "
                    "microservice was unavailable at initiation time.",
    )
    qr_svg: Optional[str] = Field(
        default=None, description="SVG markup of the same QR code."
    )
    qr_expires_at: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp the QR countdown timer should target."
    )


class MockWebhookRequest(BaseModel):
    transaction_id: str
    bank_reference_no: str = Field(..., description="Mock UTR number")
    status: str = Field(..., examples=["SUCCESS", "FAILED"])
    signature: str = Field(..., description="HMAC-SHA256 signature")


class MockWebhookSignRequest(BaseModel):
    """Convenience endpoint for the offline frontend to obtain a valid
    mock signature without embedding the shared secret in client JS."""
    transaction_id: str
    bank_reference_no: str
    status: str = "SUCCESS"


class MockWebhookSignResponse(BaseModel):
    signature: str


class InvoiceStatusOut(BaseModel):
    invoice_id: str
    invoice_status: str
    amount_paid: float
    amount_due: float


class MockWebhookResponse(BaseModel):
    transaction_id: str
    payment_status: str
    bank_reference_no: Optional[str] = None
    invoice: Optional[InvoiceStatusOut] = None


class ErrorResponse(BaseModel):
    error_code: Optional[str] = None
    message: str
    details: Optional[dict] = None
