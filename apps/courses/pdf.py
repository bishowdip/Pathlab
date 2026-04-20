"""
Certificate PDF generation using reportlab (pure Python, no system deps).

Landscape A4 with a subtle border, a big title, the student name, and the
course title + completion date. Rendered on-demand — we don't store files.
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def render_certificate_pdf(*, student_name, course_title, completed_on=None,
                           brand="PathLab", reference=""):
    completed_on = completed_on or date.today()
    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # Outer border
    c.setStrokeColor(colors.HexColor("#0F1115"))
    c.setLineWidth(2)
    c.rect(12 * mm, 12 * mm, W - 24 * mm, H - 24 * mm)
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.HexColor("#10B981"))
    c.rect(16 * mm, 16 * mm, W - 32 * mm, H - 32 * mm)

    # Brand header
    c.setFillColor(colors.HexColor("#10B981"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(22 * mm, H - 26 * mm, brand.upper())

    # Title
    c.setFillColor(colors.HexColor("#0F1115"))
    c.setFont("Helvetica-Bold", 44)
    c.drawCentredString(W / 2, H - 60 * mm, "Certificate of Completion")

    # Sub
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#525866"))
    c.drawCentredString(W / 2, H - 72 * mm, "This certifies that")

    # Name
    c.setFillColor(colors.HexColor("#0F1115"))
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(W / 2, H - 92 * mm, student_name)

    # Course
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#525866"))
    c.drawCentredString(W / 2, H - 106 * mm, "has successfully completed the course")

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(colors.HexColor("#0F1115"))
    c.drawCentredString(W / 2, H - 122 * mm, course_title)

    # Footer — date and reference
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#525866"))
    c.drawString(26 * mm, 26 * mm, f"Awarded {completed_on:%B %d, %Y}")
    if reference:
        c.drawRightString(W - 26 * mm, 26 * mm, f"Ref: {reference}")

    c.showPage()
    c.save()
    return buf.getvalue()
