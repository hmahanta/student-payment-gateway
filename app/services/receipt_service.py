"""
Module Name: receipt_service.py

Purpose:
    Generates a professional, offline PDF payment receipt for any
    SUCCESSFUL transaction, using reportlab (already a project dependency
    — no additional install, no network call, no external template
    engine). Output includes:

      - Institute logo placeholder
      - Receipt number, date, operator
      - Student + fee + payment details table
      - Amount paid, UTR / bank reference, transaction id
      - A "PAID" stamp
      - A Code128 barcode of the transaction id (for physical scanning by
        the front office)
      - A QR code encoding a compact verification payload (transaction id,
        UTR, amount) — generated in-process by reportlab's own barcode
        widget, independent of the Node.js QR microservice used for the
        payment-collection QR, since a settled receipt must be printable
        even if that microservice is offline by the time the receipt is
        requested
      - Footer text (configurable) and a digital-signature placeholder

Author:
    Harish

Version:
    1.0.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.logging_manager import get_logger

from app.config import PaymentAggregatorConfig
from app.exceptions import ReceiptNotAvailableError, TransactionNotFoundError
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.student_repository import StudentRepository

log = get_logger(__name__)


class ReceiptService:
    def __init__(
        self,
        payment_repository: PaymentRepository,
        invoice_repository: InvoiceRepository,
        student_repository: StudentRepository,
        business_config: PaymentAggregatorConfig,
        output_dir: Path,
    ) -> None:
        self._payment_repo = payment_repository
        self._invoice_repo = invoice_repository
        self._student_repo = student_repository
        self._config = business_config
        self._output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def receipt_path_for(self, transaction_id: str) -> Path:
        return self._output_dir / f"RECEIPT_{transaction_id}.pdf"

    def generate_receipt(self, transaction_id: str) -> Path:
        """
        Build (or rebuild) the PDF receipt for a settled transaction and
        return its filesystem path.

        Raises:
            TransactionNotFoundError: unknown transaction_id.
            ReceiptNotAvailableError: transaction has not settled SUCCESS.
        """
        transaction = self._payment_repo.get_by_id(transaction_id)
        if transaction is None:
            raise TransactionNotFoundError(transaction_id)
        if transaction.payment_status != "SUCCESS":
            raise ReceiptNotAvailableError(transaction_id)

        invoice = self._invoice_repo.get_by_id(transaction.invoice_id)
        student = self._student_repo.get_by_id(transaction.student_id)

        path = self.receipt_path_for(transaction_id)
        self._render_pdf(path, transaction, invoice, student)
        log.info("Receipt generated: transaction=%s path=%s", transaction_id, path)
        return path

    # ------------------------------------------------------------------
    # PDF rendering
    # ------------------------------------------------------------------

    def _render_pdf(self, path: Path, transaction, invoice, student) -> None:
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            title=f"Receipt {transaction.transaction_id}",
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReceiptTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=2
        )
        muted_style = ParagraphStyle(
            "Muted", parent=styles["Normal"], textColor=colors.HexColor("#64748b"), fontSize=9
        )
        section_style = ParagraphStyle(
            "Section", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4
        )

        story = []

        # ---- Header: logo placeholder + institute name + receipt no. ----
        header_table = Table(
            [
                [
                    self._logo_placeholder(),
                    Paragraph(
                        f"<b>{self._config.merchant_name}</b><br/>"
                        f"<font size=9 color='#64748b'>Fee Payment Receipt</font>",
                        title_style,
                    ),
                    Paragraph(
                        f"<b>Receipt No:</b> RCPT-{transaction.transaction_id}<br/>"
                        f"<b>Date:</b> {self._format_dt(transaction.completed_at)}<br/>"
                        f"<b>Operator:</b> SYSTEM (Auto-Reconciled)",
                        muted_style,
                    ),
                ]
            ],
            colWidths=[22 * mm, 90 * mm, 62 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 10 * mm))

        # ---- Student details ----
        story.append(Paragraph("Student Details", section_style))
        student_rows = [
            ["Student ID", student.student_id, "Student Name", student.student_name],
            ["Email", student.email or "-", "Phone", student.phone_number or "-"],
        ]
        story.append(self._detail_table(student_rows))

        # ---- Fee / invoice details ----
        story.append(Paragraph("Fee Details", section_style))
        fee_rows = [
            ["Invoice No", invoice.invoice_id, "Academic Term", invoice.academic_term or "-"],
            ["Description", invoice.fee_description, "Invoice Status", invoice.invoice_status],
        ]
        story.append(self._detail_table(fee_rows))

        # ---- Payment details ----
        story.append(Paragraph("Payment Details", section_style))
        payment_rows = [
            ["Transaction ID", transaction.transaction_id, "Payment Mode", transaction.payment_mode],
            [
                "Amount Paid",
                f"Rs. {transaction.amount_paid:,.2f}",
                "Bank Reference (UTR)",
                transaction.bank_reference_no or "-",
            ],
            [
                "Initiated At",
                self._format_dt(transaction.initiated_at),
                "Settled At",
                self._format_dt(transaction.completed_at),
            ],
        ]
        story.append(self._detail_table(payment_rows))
        story.append(Spacer(1, 8 * mm))

        # ---- PAID stamp + barcode + QR row ----
        stamp = self._paid_stamp()
        barcode_drawing = self._barcode_drawing(transaction.transaction_id)
        qr_drawing = self._qr_drawing(transaction, invoice)

        codes_table = Table(
            [[stamp, barcode_drawing, qr_drawing]],
            colWidths=[45 * mm, 65 * mm, 45 * mm],
        )
        codes_table.setStyle(
            TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")])
        )
        story.append(codes_table)
        story.append(Spacer(1, 10 * mm))

        # ---- Digital signature placeholder ----
        sig_table = Table(
            [["", "____________________________"], ["", "Authorised Signatory (Digital Signature Placeholder)"]],
            colWidths=[110 * mm, 64 * mm],
        )
        sig_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "CENTER")]))
        story.append(sig_table)
        story.append(Spacer(1, 6 * mm))

        # ---- Footer ----
        story.append(
            Paragraph(
                f"<font size=8 color='#94a3b8'>{self._config.receipt_footer_text}</font>",
                muted_style,
            )
        )
        story.append(
            Paragraph(
                "<font size=7 color='#cbd5e1'>Generated offline by the Student Smart Payment "
                "Aggregator — no external gateway involved.</font>",
                muted_style,
            )
        )

        doc.build(story)

    # ------------------------------------------------------------------
    # Small drawing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detail_table(rows: list[list[str]]) -> Table:
        table = Table(rows, colWidths=[32 * mm, 62 * mm, 32 * mm, 48 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#475569")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        return table

    @staticmethod
    def _logo_placeholder() -> Drawing:
        from reportlab.graphics.shapes import Rect, String

        d = Drawing(20 * mm, 20 * mm)
        d.add(Rect(0, 0, 20 * mm, 20 * mm, strokeColor=colors.HexColor("#cbd5e1"), fillColor=colors.HexColor("#f1f5f9")))
        d.add(String(10 * mm, 9 * mm, "LOGO", fontSize=7, fillColor=colors.HexColor("#94a3b8"), textAnchor="middle"))
        return d

    @staticmethod
    def _paid_stamp() -> Drawing:
        from reportlab.graphics.shapes import Group, Rect, String

        d = Drawing(40 * mm, 20 * mm)
        group = Group()
        group.add(
            Rect(
                0, 0, 40 * mm, 16 * mm,
                strokeColor=colors.HexColor("#dc2626"),
                fillColor=colors.white,
                strokeWidth=2,
            )
        )
        group.add(
            String(
                20 * mm, 6 * mm, "PAID",
                fontSize=18, fontName="Helvetica-Bold",
                fillColor=colors.HexColor("#dc2626"), textAnchor="middle",
            )
        )
        group.rotate(6)
        d.add(group)
        return d

    @staticmethod
    def _barcode_drawing(transaction_id: str):
        # reportlab's Code128 is itself a platypus Flowable (not a Shape),
        # so it goes straight into a Table cell / story — no Drawing needed.
        return code128.Code128(transaction_id, barHeight=14 * mm, barWidth=0.35 * mm)

    @staticmethod
    def _qr_drawing(transaction, invoice) -> Drawing:
        payload = (
            f"RCPT|{transaction.transaction_id}|{transaction.bank_reference_no or ''}|"
            f"{transaction.amount_paid}|{invoice.invoice_id}"
        )
        widget = qr.QrCodeWidget(payload)
        bounds = widget.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        size = 28 * mm
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(widget)
        return d

    @staticmethod
    def _format_dt(value: Optional[datetime]) -> str:
        if value is None:
            return "-"
        return value.strftime("%d-%b-%Y %H:%M:%S")
