"""
Module Name: test_payment_flow.py

Purpose:
    Integration tests against a real local Oracle XE instance (via the
    reviewed framework's DatabaseManager) exercising the full payment
    lifecycle: student lookup -> initiate payment -> mock bank webhook ->
    invoice reconciliation.

    Requires a running Oracle XE with the schema from sql/01_create_tables.sql
    and sql/02_seed_sample_data.sql already applied, and a valid .env file.
    These are integration, not unit, tests — by design, per the offline
    testing requirement (no mocking of the Oracle connection itself).

Author:
    Harish

Version:
    1.0.0

Run:
    pytest tests/ -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.bootstrap import Bootstrap
from app.models.orm_models import FeeInvoice


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _create_fresh_invoice(student_id: str, amount_due: str = "1000.00") -> str:
    """
    Insert a brand-new, always-pending invoice for the given student so
    payment-flow tests are idempotent across repeated runs — they never
    depend on seed data (sql/02_seed_sample_data.sql) still being unpaid,
    which stops being true after the first successful test run.
    """
    services = Bootstrap.get_services()
    invoice_id = f"TESTINV{uuid.uuid4().hex[:12].upper()}"
    with services.ctx.db.session() as sess:
        sess.add(
            FeeInvoice(
                invoice_id=invoice_id,
                student_id=student_id,
                fee_description="Automated Test Invoice",
                academic_term="TEST",
                amount_due=Decimal(amount_due),
                amount_paid=Decimal("0"),
                invoice_status="PENDING",
            )
        )
    return invoice_id


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "overall_status" in body
    assert any(c["name"] == "Mock Bank Simulator" for c in body["checks"])


def test_list_students(client):
    resp = client.get("/api/students")
    assert resp.status_code == 200
    students = resp.json()
    assert any(s["student_id"] == "STU1001" for s in students)


def test_get_student_profile(client):
    resp = client.get("/api/students/STU1001/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["student"]["student_id"] == "STU1001"
    assert len(body["pending_invoices"]) >= 1


def test_student_not_found(client):
    resp = client.get("/api/students/DOES_NOT_EXIST/profile")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "PAY-404-STU"


def test_full_upi_payment_and_webhook_flow(client):
    # 1. Create a fresh, guaranteed-pending invoice for this run (don't
    #    depend on seed data — earlier successful runs may have already
    #    paid off the seeded invoices).
    invoice_id = _create_fresh_invoice("STU1002", amount_due="45000.00")
    profile = client.get("/api/students/STU1002/profile").json()
    pending = profile["pending_invoices"]
    match = next(i for i in pending if i["invoice_id"] == invoice_id)
    outstanding_before = match["amount_due"] - match["amount_paid"]

    # 2. Initiate a UPI_QR payment.
    init_resp = client.post(
        "/api/payments/initiate",
        json={
            "student_id": "STU1002",
            "invoice_id": invoice_id,
            "payment_mode": "UPI_QR",
        },
    )
    assert init_resp.status_code == 200
    init_body = init_resp.json()
    assert init_body["payment_status"] == "PENDING"
    assert init_body["upi_uri"].startswith("upi://pay?")
    transaction_id = init_body["transaction_id"]

    # 3. Generate a mock UTR + valid signature (as the frontend would).
    utr_resp = client.get("/api/mock-bank/generate-utr")
    utr = utr_resp.json()["utr"]

    sign_resp = client.post(
        "/api/mock-bank/sign",
        json={
            "transaction_id": transaction_id,
            "bank_reference_no": utr,
            "status": "SUCCESS",
        },
    )
    signature = sign_resp.json()["signature"]

    # 4. Fire the mock bank webhook.
    webhook_resp = client.post(
        "/api/mock-bank/webhook",
        json={
            "transaction_id": transaction_id,
            "bank_reference_no": utr,
            "status": "SUCCESS",
            "signature": signature,
        },
    )
    assert webhook_resp.status_code == 200
    webhook_body = webhook_resp.json()
    assert webhook_body["payment_status"] == "SUCCESS"
    assert webhook_body["bank_reference_no"] == utr
    assert webhook_body["invoice"]["invoice_id"] == invoice_id
    assert webhook_body["invoice"]["amount_paid"] == pytest.approx(
        match["amount_paid"] + outstanding_before
    )

    # 5. Duplicate webhook must be rejected (idempotency / no double-credit).
    dup_resp = client.post(
        "/api/mock-bank/webhook",
        json={
            "transaction_id": transaction_id,
            "bank_reference_no": utr,
            "status": "SUCCESS",
            "signature": signature,
        },
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["error_code"] == "PAY-409-DUP"


def test_webhook_rejects_bad_signature(client):
    invoice_id = _create_fresh_invoice("STU1001", amount_due="500.00")

    init_body = client.post(
        "/api/payments/initiate",
        json={"student_id": "STU1001", "invoice_id": invoice_id, "payment_mode": "UPI_ID"},
    ).json()

    bad_resp = client.post(
        "/api/mock-bank/webhook",
        json={
            "transaction_id": init_body["transaction_id"],
            "bank_reference_no": "MOCKUTR000000000000",
            "status": "SUCCESS",
            "signature": "deadbeef" * 8,
        },
    )
    assert bad_resp.status_code == 401
    assert bad_resp.json()["error_code"] == "PAY-401-SIG"
