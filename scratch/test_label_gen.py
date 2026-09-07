import io
import base64
from reportlab.lib.pagesizes import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128
from reportlab.graphics.shapes import Drawing

def generate_shipglobal_thermal_label_pdf(
    waybill: str,
    order_ref: str,
    service_code: str,
    consignee_name: str,
    consignee_address: str,
    consignee_city: str,
    consignee_state: str,
    consignee_zip: str,
    consignee_country: str,
    consignee_phone: str,
    seller_name: str = "The Saveur",
    seller_address: str = "Flat 4/226, Jawahar Nagar",
    seller_city: str = "Jaipur, RJ 302004, IN",
    items_desc: str = "Gourmet Foods / Pantry Items",
    weight_kg: float = 0.5,
    value_str: str = "USD 35.00"
) -> str:
    """
    Generates an authentic 4x6 inch thermal shipping label as a Base64-encoded PDF.
    """
    width = 4 * inch   # 288 pt
    height = 6 * inch  # 432 pt
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    # Outer border
    c.setLineWidth(1.5)
    c.setStrokeColor(colors.black)
    c.rect(10, 10, width - 20, height - 20)

    # Carrier header banner
    c.setFillColor(colors.black)
    c.rect(10, height - 52, width - 20, 42, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(18, height - 32, "SHIPGLOBAL")
    
    c.setFont("Helvetica-Bold", 10)
    service_display = service_code.replace("-CLASSIC", "").replace("-", " ")
    c.drawRightString(width - 18, height - 30, f"{service_display} EXPRESS")
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 18, height - 44, "INTL PRIORITY AIR CARGO")

    # Routing line
    c.setFillColor(colors.black)
    c.line(10, height - 52, width - 10, height - 52)
    
    # Sort Code Box
    c.setFont("Helvetica-Bold", 18)
    dest_hub = f"{consignee_country.upper()}-{consignee_zip[:3]}"
    c.drawString(18, height - 76, dest_hub)
    c.setFont("Helvetica", 8)
    c.drawString(18, height - 88, f"SERVICE: {service_code}")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(width - 18, height - 76, "CSB-V COMMERCIAL")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 18, height - 88, f"WT: {weight_kg:.2f} KG")

    # Divider
    c.setLineWidth(1)
    c.line(10, height - 96, width - 10, height - 96)

    # Barcode Section
    try:
        from reportlab.graphics.barcode import createBarcodeDrawing
        d = createBarcodeDrawing('Code128', value=str(waybill).strip(), barHeight=38, barWidth=1.2, humanReadable=False)
        # Center horizontally
        draw_x = max(18, (width - d.width) / 2)
        d.drawOn(c, draw_x, height - 150)
    except Exception as e:
        print("Barcode render error:", e)

    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width / 2, height - 162, f"TRACKING #: {waybill}")

    # Divider
    c.line(10, height - 172, width - 10, height - 172)

    # Ship To Box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 186, "SHIP TO (CONSIGNEE):")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18, height - 200, consignee_name[:32])
    
    c.setFont("Helvetica", 8.5)
    addr_y = height - 214
    for line in [consignee_address[:40], f"{consignee_city}, {consignee_state} {consignee_zip}", f"COUNTRY: {consignee_country.upper()}"]:
        if line.strip():
            c.drawString(18, addr_y, line)
            addr_y -= 12
    c.drawString(18, addr_y, f"PHONE: {consignee_phone}")

    # Divider
    c.line(10, height - 275, width - 10, height - 275)

    # From (Shipper) Box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 289, "FROM (SHIPPER):")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18, height - 302, seller_name)
    c.setFont("Helvetica", 8)
    c.drawString(18, height - 314, seller_address)
    c.drawString(18, height - 325, seller_city)

    # Divider
    c.line(10, height - 335, width - 10, height - 335)

    # Customs & Order reference box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 349, "CUSTOMS DECLARATION / CSB-V DETAILS:")
    c.setFont("Helvetica", 7.5)
    c.drawString(18, height - 361, f"REF ORDER: {order_ref}")
    c.drawString(18, height - 373, f"CONTENTS: {items_desc[:35]}")
    c.drawString(18, height - 385, f"HSN: 21069099 | VALUE: {value_str}")
    c.drawString(18, height - 397, "ORIGIN: INDIA (IN) | TERMS: DDU")

    # Bottom footer
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(colors.gray)
    c.drawCentredString(width / 2, 16, "OFFICIAL THERMAL 4X6 CARRIER LABEL • SHIPGLOBAL INTEGRATED NETWORK")

    c.showPage()
    c.save()
    pdf_data = buf.getvalue()
    buf.close()
    return base64.b64encode(pdf_data).decode('ascii')

if __name__ == "__main__":
    b64 = generate_shipglobal_thermal_label_pdf(
        waybill="UUS950052907601",
        order_ref="ORD-2026-0012",
        service_code="DHLECS-CLASSIC",
        consignee_name="John Doe",
        consignee_address="742 Evergreen Terrace",
        consignee_city="Springfield",
        consignee_state="OR",
        consignee_zip="97477",
        consignee_country="US",
        consignee_phone="+1-555-0199"
    )
    print("PDF base64 length:", len(b64))
    assert len(b64) > 1000
    print("Label generation test PASSED!")
