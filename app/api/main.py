"""
Module Name: main.py

Purpose:
    FastAPI application for the Student Smart Payment Aggregator.
    Exposes:
      GET  /api/students                              - list active students
      GET  /api/students/{student_id}/profile          - profile + pending invoices
      POST /api/payments/initiate                       - initiate a payment (UPI/net banking)
      POST /api/mock-bank/sign                            - convenience: sign a mock webhook payload
      POST /api/mock-bank/webhook                          - simulated bank success/failure callback
      GET  /api/payments/{transaction_id}                   - transaction status lookup
      GET  /api/health                                       - merged framework + business health report

    All routes depend on app.bootstrap.Bootstrap.get_services() for the
    wired service graph — no route constructs a service itself.

Author:
    Harish

Version:
    1.0.0

Run (offline, local):
    uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.exception_manager import ApplicationError
from core.logging_manager import get_logger

from app.bootstrap import AppServices, Bootstrap
from app.constants import PaymentMode
from app.services.mock_bank_service import MockBankService
from app.api.schemas import (
    ErrorResponse,
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    InvoiceOut,
    InvoiceStatusOut,
    MockWebhookRequest,
    MockWebhookResponse,
    MockWebhookSignRequest,
    MockWebhookSignResponse,
    StudentOut,
    StudentProfileResponse,
)

log = get_logger(__name__)

app = FastAPI(
    title="Student Smart Payment Aggregator",
    version="1.0.0",
    description="Offline, ERP-neutral fee payment aggregator built on the enterprise AI framework.",
)

# Local offline testing only — the single-file HTML frontend is served from
# disk (file://) or a simple static server, so CORS is opened permissively.
# Tighten this before any non-local deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_services() -> AppServices:
    return Bootstrap.get_services()


@app.exception_handler(ApplicationError)
async def application_error_handler(request: Request, exc: ApplicationError):
    """
    Maps the framework's typed exception hierarchy to HTTP responses.
    Domain 404-style errors -> 404, validation/signature errors -> 4xx,
    everything else -> 500. Centralised here so no route handler needs its
    own try/except for these types.
    """
    status_map = {
        "PAY-404-STU": 404,
        "PAY-404-INV": 404,
        "PAY-404-TXN": 404,
        "PAY-409-INV": 409,
        "PAY-409-DUP": 409,
        "PAY-401-SIG": 401,
        "PAY-422-VAL": 422,
    }
    http_status = status_map.get(exc.error_code, 500)
    log.warning("ApplicationError handled: %s", exc.to_dict())
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse(
            error_code=exc.error_code, message=exc.message, details=exc.details
        ).model_dump(),
    )


# ----------------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    services = get_services()
    report = services.ctx.health_report.to_dict()

    # Supplementary business check, merged additively — health_check_manager
    # is not modified.
    mock_bank_check = {
        "name": "Mock Bank Simulator",
        "status": "PASS",
        "message": "Mock bank webhook signing is in-process and always reachable offline.",
    }
    report["checks"].append(mock_bank_check)
    return report


# ----------------------------------------------------------------------------
# Students
# ----------------------------------------------------------------------------

@app.get("/api/students", response_model=list[StudentOut])
def list_students():
    services = get_services()
    students = services.student_service.list_active_students()
    return [
        StudentOut(
            student_id=s.student_id,
            student_name=s.student_name,
            assigned_virtual_account=s.assigned_virtual_account,
            assigned_ifsc=s.assigned_ifsc,
            assigned_upi_id=s.assigned_upi_id,
        )
        for s in students
    ]


@app.get("/api/students/{student_id}/profile", response_model=StudentProfileResponse)
def get_student_profile(student_id: str):
    services = get_services()
    student = services.student_service.get_student(student_id)
    invoices = services.invoice_service.get_pending_invoices_for_student(student_id)

    return StudentProfileResponse(
        student=StudentOut(
            student_id=student.student_id,
            student_name=student.student_name,
            assigned_virtual_account=student.assigned_virtual_account,
            assigned_ifsc=student.assigned_ifsc,
            assigned_upi_id=student.assigned_upi_id,
        ),
        pending_invoices=[
            InvoiceOut(
                invoice_id=inv.invoice_id,
                fee_description=inv.fee_description,
                amount_due=float(inv.amount_due),
                amount_paid=float(inv.amount_paid),
                invoice_status=inv.invoice_status,
                due_date=inv.due_date,
            )
            for inv in invoices
        ],
    )


# ----------------------------------------------------------------------------
# Payments
# ----------------------------------------------------------------------------

@app.post("/api/payments/initiate", response_model=InitiatePaymentResponse)
def initiate_payment(payload: InitiatePaymentRequest):
    services = get_services()
    try:
        mode = PaymentMode(payload.payment_mode)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid payment_mode '{payload.payment_mode}'. "
                   f"Expected one of {[m.value for m in PaymentMode]}.",
        )

    result = services.payment_service.initiate_payment(
        student_id=payload.student_id,
        invoice_id=payload.invoice_id,
        payment_mode=mode,
    )
    return InitiatePaymentResponse(**result)


@app.get("/api/payments/{transaction_id}")
def get_payment_status(transaction_id: str):
    services = get_services()
    txn = services.payment_service.get_transaction(transaction_id)
    return {
        "transaction_id": txn.transaction_id,
        "payment_status": txn.payment_status,
        "bank_reference_no": txn.bank_reference_no,
        "amount_paid": float(txn.amount_paid),
        "payment_mode": txn.payment_mode,
    }


# ----------------------------------------------------------------------------
# Mock Bank Simulator
# ----------------------------------------------------------------------------

@app.post("/api/mock-bank/sign", response_model=MockWebhookSignResponse)
def sign_mock_webhook(payload: MockWebhookSignRequest):
    """
    Convenience endpoint ONLY for offline testing: lets the frontend's
    'Simulate Payment Success' button obtain a correctly-signed payload
    without embedding the shared webhook secret in client-side JS.
    A real bank integration would never expose this — the bank itself
    signs the callback with a secret only it and the merchant know.
    """
    services = get_services()
    mock_bank: MockBankService = services.mock_bank_service
    signature = mock_bank.sign_payload(
        payload.transaction_id, payload.bank_reference_no, payload.status
    )
    return MockWebhookSignResponse(signature=signature)


@app.post("/api/mock-bank/webhook", response_model=MockWebhookResponse)
def mock_bank_webhook(payload: MockWebhookRequest):
    """
    Simulates the bank's asynchronous payment-status callback. Verifies the
    HMAC signature, then atomically commits the transaction status and the
    invoice balance update in a single DatabaseManager session.
    """
    services = get_services()
    result = services.payment_service.reconcile_webhook(
        transaction_id=payload.transaction_id,
        bank_reference_no=payload.bank_reference_no,
        status=payload.status,
        signature=payload.signature,
    )
    invoice_out = (
        InvoiceStatusOut(**result["invoice"]) if result.get("invoice") else None
    )
    return MockWebhookResponse(
        transaction_id=result["transaction_id"],
        payment_status=result["payment_status"],
        bank_reference_no=result.get("bank_reference_no"),
        invoice=invoice_out,
    )


@app.get("/api/mock-bank/generate-utr")
def generate_mock_utr():
    """Convenience endpoint: returns a random mock UTR for the frontend demo button."""
    return {"utr": MockBankService.generate_utr()}
