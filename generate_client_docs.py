"""
Generate Complete, Enterprise-Grade Client Documentation PDF for The Saveur Platform.
Uses ReportLab with high-fidelity corporate styling, emerald & gold brand palette,
two-pass NumberedCanvas for dynamic 'Page X of Y' pagination, running headers/footers,
and comprehensive technical and functional specifications.
"""

import os
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            # Skip header and footer on cover page
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#064E3B"))

        # Running Header
        self.drawString(40, 812, "THE SAVEUR — COMPLETE PLATFORM DOCUMENTATION & TECHNICAL HANDOVER")
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawRightString(555, 812, "CONFIDENTIAL & PROPRIETARY")

        # Header rule
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 804, 555, 804)

        # Footer rule
        self.line(40, 42, 555, 42)

        # Running Footer
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(40, 30, "The Saveur E-Commerce Platform | Complete Client Reference Manual v2.4")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(555, 30, page_str)

        self.restoreState()


def build_pdf(filename="The_Saveur_Complete_Client_Documentation.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=48,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Brand Colors
    PRIMARY = colors.HexColor("#064E3B")       # Deep Forest Emerald
    PRIMARY_LIGHT = colors.HexColor("#ECFDF5") # Soft Mint
    PRIMARY_DARK = colors.HexColor("#022C22")
    SECONDARY = colors.HexColor("#B45309")     # Warm Amber Gold
    DARK_TEXT = colors.HexColor("#0F172A")     # Deep Charcoal
    BODY_TEXT = colors.HexColor("#334155")     # Slate 700
    MUTED_TEXT = colors.HexColor("#64748B")    # Slate 500
    BG_LIGHT = colors.HexColor("#F8FAFC")      # Slate 50
    BORDER_COLOR = colors.HexColor("#CBD5E1")  # Slate 300
    SUCCESS_GREEN = colors.HexColor("#047857")
    AMBER_BG = colors.HexColor("#FFFBEB")
    AMBER_BORDER = colors.HexColor("#FDE68A")

    # Typography Styles
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=PRIMARY,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=MUTED_TEXT,
        spaceAfter=15
    )

    meta_label = ParagraphStyle(
        'CoverMetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=PRIMARY
    )

    meta_val = ParagraphStyle(
        'CoverMetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=BODY_TEXT
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=PRIMARY,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        'Heading3_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=DARK_TEXT,
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=BODY_TEXT,
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=BODY_TEXT,
        leftIndent=10,
        firstLineIndent=-6,
        spaceAfter=2.5
    )

    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.white
    )

    table_body = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=DARK_TEXT
    )

    table_body_bold = ParagraphStyle(
        'TableBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=PRIMARY
    )

    callout_text = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#065F46")
    )

    badge_cod = ParagraphStyle(
        'BadgeCOD', fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor("#92400E")
    )
    badge_prepaid = ParagraphStyle(
        'BadgePrepaid', fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor("#065F46")
    )
    badge_paypal = ParagraphStyle(
        'BadgePayPal', fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=colors.HexColor("#1E40AF")
    )

    story = []

    # =========================================================================
    # PAGE 1: COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 20))
    
    brand_pill = Table(
        [[Paragraph("<b>THE SAVEUR</b> &nbsp;|&nbsp; GOURMET ARTISAN FOODS &amp; HEALTHY SNACKS", ParagraphStyle(
            'BrandPill', fontName='Helvetica-Bold', fontSize=9, textColor=PRIMARY
        ))]],
        colWidths=[515]
    )
    brand_pill.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY_LIGHT),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#A7F3D0")),
    ]))
    story.append(brand_pill)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Enterprise Platform Documentation &amp; Technical Manual", title_style))
    story.append(Paragraph("Comprehensive Architectural Blueprint, Feature Manual, Security Framework, Logistics Guide &amp; System Administration Handover", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=18))

    exec_summary_cover = Table(
        [[Paragraph(
            "<b>PLATFORM OVERVIEW:</b> The Saveur is an enterprise-grade direct-to-consumer (D2C) e-commerce system built with Python Flask, SQLite/PostgreSQL, Redis caching, Celery task queuing, and multi-gateway payment processing. This complete reference document details all client-facing features, administrative controls, logistics lifecycle tracking, automated tax invoicing, security architectures, and operations protocols.",
            callout_text
        )]],
        colWidths=[515]
    )
    exec_summary_cover.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY_LIGHT),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#10B981")),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(exec_summary_cover)
    story.append(Spacer(1, 22))

    meta_data = [
        [Paragraph("Project Name:", meta_label), Paragraph("The Saveur E-Commerce Web Platform", meta_val),
         Paragraph("Document Version:", meta_label), Paragraph("v2.4 (Production Release)", meta_val)],
        [Paragraph("Client / Owner:", meta_label), Paragraph("The Saveur Gourmet Foods", meta_val),
         Paragraph("Release Date:", meta_label), Paragraph("September 2026", meta_val)],
        [Paragraph("Primary Framework:", meta_label), Paragraph("Python 3.12 / Flask 3.1", meta_val),
         Paragraph("Security Model:", meta_label), Paragraph("HMAC-SHA256 / Alphanumeric Refs", meta_val)],
        [Paragraph("Database Engine:", meta_label), Paragraph("SQLite 3 (WAL Mode) / PostgreSQL", meta_val),
         Paragraph("Logistics Engine:", meta_label), Paragraph("5-Stage Dynamic Multi-Courier", meta_val)],
        [Paragraph("Payment Gateways:", meta_label), Paragraph("Razorpay (UPI/Cards) + PayPal + COD", meta_val),
         Paragraph("Task Queuing:", meta_label), Paragraph("Celery + RabbitMQ / Redis", meta_val)],
    ]
    meta_table = Table(meta_data, colWidths=[110, 155, 105, 145])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 28))

    confidential_note = Paragraph(
        "<b>CONFIDENTIALITY NOTICE:</b> The information contained in this technical document is proprietary and confidential to The Saveur. It contains intellectual property, system architecture secrets, database schemas, and operational instructions. Unauthorized duplication or distribution is strictly prohibited.",
        ParagraphStyle('ConfNote', fontName='Helvetica-Oblique', fontSize=7.5, leading=10.5, textColor=MUTED_TEXT, alignment=1)
    )
    story.append(confidential_note)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: TABLE OF CONTENTS & SECTION 1
    # =========================================================================
    story.append(Paragraph("Table of Contents", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    toc_data = [
        [Paragraph("<b>Section 1:</b> Executive Summary & Platform Highlights", table_body_bold), Paragraph("Page 2", table_body)],
        [Paragraph("<b>Section 2:</b> System Architecture & Technical Specifications", table_body_bold), Paragraph("Page 3", table_body)],
        [Paragraph("<b>Section 3:</b> Storefront Features & Customer Journey", table_body_bold), Paragraph("Page 4", table_body)],
        [Paragraph("<b>Section 4:</b> End-to-End Logistics & 5-Stage Live Order Tracking", table_body_bold), Paragraph("Page 5", table_body)],
        [Paragraph("<b>Section 5:</b> Automated Single-Page Invoicing & Tax Compliance", table_body_bold), Paragraph("Page 6", table_body)],
        [Paragraph("<b>Section 6:</b> Transactional Email System & Notification Dispatch", table_body_bold), Paragraph("Page 7", table_body)],
        [Paragraph("<b>Section 7:</b> Security Framework, Cryptographic Tokens & Authorization", table_body_bold), Paragraph("Page 8", table_body)],
        [Paragraph("<b>Section 8:</b> Administrative Control Portal & Operations Manual", table_body_bold), Paragraph("Page 9", table_body)],
        [Paragraph("<b>Section 9:</b> Database Relational Schema & Entity Specifications", table_body_bold), Paragraph("Page 10", table_body)],
        [Paragraph("<b>Section 10:</b> API Directory, Routing Architecture & Endpoints", table_body_bold), Paragraph("Page 11", table_body)],
        [Paragraph("<b>Section 11:</b> Deployment, Environment Variables & Maintenance Guide", table_body_bold), Paragraph("Page 12", table_body)],
        [Paragraph("<b>Section 12:</b> Client Deliverables Sign-Off & Handover", table_body_bold), Paragraph("Page 13", table_body)],
    ]
    toc_table = Table(toc_data, colWidths=[430, 85])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(toc_table)
    story.append(Spacer(1, 10))

    # SECTION 1: EXECUTIVE SUMMARY
    story.append(Paragraph("1. Executive Summary & Core Platform Capabilities", h1_style))
    story.append(Paragraph(
        "The Saveur web platform is a custom-engineered, full-featured direct-to-consumer (D2C) e-commerce application designed to deliver an opulent shopping experience for artisanal gourmet snacks, roasted makhanas, cookies, and premium dry fruits. The application seamlessly bridges client engagement, ultra-fast browsing, multi-gateway checkout, automated logistics dispatch, and strict data security.",
        body_style
    ))
    story.append(Paragraph("Key Core Capabilities & Recent Enhancements:", h2_style))
    story.append(Paragraph("&bull; <b>High-Speed Responsive Storefront:</b> Clean, modern aesthetic with rich typography, mobile-first responsive layouts, interactive hero carousels, dynamic product filters, and live search.", bullet_style))
    story.append(Paragraph("&bull; <b>5-Stage Real-Time Logistics Lifecycle:</b> Complete status synchronization across <i>Order Confirmed &rarr; Shipped &rarr; In Transit &rarr; Out for Delivery &rarr; Delivered</i> with dynamic multi-courier tracking links (Blue Dart, Delhivery, DTDC, India Post, etc.).", bullet_style))
    story.append(Paragraph("&bull; <b>Automated Single-Page Tax Invoicing:</b> Print-optimized A4 tax receipts strictly formatted to single-page dimensions, containing complete FSSAI No. compliance, GST breakdown, QR verification, and color-highlighted payment methods.", bullet_style))
    story.append(Paragraph("&bull; <b>Cryptographic Security & Alphanumeric IDs:</b> Non-guessable order references (<code>TSV-A3X9KZ2Q</code>), customer-specific authorization preventing unauthorized access (IDOR protection), and HMAC-SHA256 direct access tokens for seamless, passwordless email tracking.", bullet_style))
    story.append(Paragraph("&bull; <b>Professional Transactional Email Communications:</b> Completely de-emojified, executive-grade email notifications dispatched asynchronously via Celery + RabbitMQ with instant fallback.", bullet_style))
    story.append(Paragraph("&bull; <b>Omnichannel Payment Highlighting:</b> Clear, color-coded visual badges for Cash on Delivery (COD), Prepaid (Razorpay / UPI), and PayPal across the Admin Console, Customer Orders, Tracking, Invoices, and Checkout.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: SYSTEM ARCHITECTURE
    # =========================================================================
    story.append(Paragraph("2. System Architecture & Technical Specifications", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))
    story.append(Paragraph(
        "The application is architected around a modular Flask backend utilizing the Application Factory and Blueprint design patterns. This ensures clean separation of concerns, high maintainability, and horizontal scalability.",
        body_style
    ))

    arch_table_data = [
        [Paragraph("Layer / Component", table_header), Paragraph("Technology Stack", table_header), Paragraph("Functional Role & Description", table_header)],
        [Paragraph("Web Server & Proxy", table_body_bold), Paragraph("Nginx / HTTP/2 / SSL", table_body), Paragraph("Terminates TLS/SSL, serves static assets (CSS, JS, WebP images) with gzip compression, reverse-proxies requests to Gunicorn.", table_body)],
        [Paragraph("WSGI Application Server", table_body_bold), Paragraph("Gunicorn / Flask 3.1.3", table_body), Paragraph("Multi-worker Python WSGI server executing route controllers, Jinja2 template rendering, authentication, and business logic.", table_body)],
        [Paragraph("In-Memory Cache", table_body_bold), Paragraph("Redis 8.0+", table_body), Paragraph("High-speed key-value cache storing navigation categories, product catalogs, and state shipping rates with auto-invalidation on updates.", table_body)],
        [Paragraph("Task Queue & Broker", table_body_bold), Paragraph("Celery 5.6 + RabbitMQ", table_body), Paragraph("Asynchronous background queue handling SMTP email dispatch (OTPs, order confirmations, shipping updates) without blocking HTTP requests.", table_body)],
        [Paragraph("Database Engine", table_body_bold), Paragraph("SQLite 3 (WAL Mode) / PostgreSQL", table_body), Paragraph("ACID-compliant relational database holding users, products, orders, coupons, reviews, and logs. Configured with Write-Ahead Logging.", table_body)],
        [Paragraph("Payment Gateways", table_body_bold), Paragraph("Razorpay REST + PayPal SDK", table_body), Paragraph("Cryptographically verified payment gateways supporting UPI, Credit/Debit Cards, Net Banking, Wallets, and International payments.", table_body)],
    ]
    arch_table = Table(arch_table_data, colWidths=[110, 115, 290])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Key Architectural Advantages:", h2_style))
    story.append(Paragraph("&bull; <b>Zero-Lag Background Processing:</b> Email delivery takes place in background worker threads; customers experience instantaneous checkout without waiting for SMTP handshakes.", bullet_style))
    story.append(Paragraph("&bull; <b>Resilient Graceful Fallbacks:</b> If Redis or RabbitMQ are temporarily unreachable, the application automatically catches exceptions and falls back to direct database queries and synchronous email delivery without user interruption.", bullet_style))
    story.append(Paragraph("&bull; <b>Modular Directory Structure:</b> Code is organized into dedicated service layers (<code>services/</code>), modular blueprints (<code>routes/</code>), context processors, database managers, and clean Jinja2 template components.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: STOREFRONT & CUSTOMER JOURNEY
    # =========================================================================
    story.append(Paragraph("3. Storefront Features & Customer Journey", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The customer experience has been engineered for maximum conversion, visual delight, and effortless navigation across all desktop, tablet, and mobile devices.",
        body_style
    ))

    storefront_steps = [
        [Paragraph("Journey Stage", table_header), Paragraph("Key Features & Capabilities", table_header), Paragraph("Customer Benefit", table_header)],
        [Paragraph("1. Discovery & Browsing", table_body_bold), Paragraph("Interactive hero carousel, category grids, subcategory filtering, live search with instant suggestions, bestseller highlight badges.", table_body), Paragraph("Effortless product discovery and brand engagement.", table_body)],
        [Paragraph("2. Product Evaluation", table_body_bold), Paragraph("Multi-angle image gallery with zoom, unit weight specs (e.g., 85g Jar), stock availability badges, discount pricing comparison, verified customer reviews.", table_body), Paragraph("Clear purchasing context and confidence.", table_body)],
        [Paragraph("3. Cart & Wishlist", table_body_bold), Paragraph("Persistent cart across sessions, one-click quantity adjustments, coupon code validator with real-time discount calculation, state-based shipping calculator.", table_body), Paragraph("Transparent pricing with zero checkout surprises.", table_body)],
        [Paragraph("4. Secure Checkout", table_body_bold), Paragraph("Dual-step checkout: Shipping Address & Contact details, followed by Payment Selection (Razorpay UPI/Cards, PayPal, or Cash on Delivery).", table_body), Paragraph("Frictionless, flexible payment options for domestic & NRI customers.", table_body)],
        [Paragraph("5. Post-Purchase", table_body_bold), Paragraph("Instant order confirmation page, alphanumeric reference ID, downloadable single-page tax invoice, and live multi-courier tracking link.", table_body), Paragraph("Immediate reassurance and transparent delivery visibility.", table_body)],
    ]
    sf_table = Table(storefront_steps, colWidths=[110, 245, 160])
    sf_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(sf_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Highlighting of Payment Methods Across the Storefront:", h2_style))
    story.append(Paragraph(
        "Every touchpoint in the customer journey clearly identifies the payment mode used with branded visual pill tags:",
        body_style
    ))
    pay_badge_table_data = [
        [Paragraph("Payment Method", table_header), Paragraph("Visual Pill Styling", table_header), Paragraph("Usage & Verification", table_header)],
        [Paragraph("Cash on Delivery (COD)", table_body_bold), Paragraph("<font color='#92400E'><b>[ Amber Pill: Cash on Delivery ]</b></font>", table_body), Paragraph("Pay upon delivery. Supported across all major postal pin codes.", table_body)],
        [Paragraph("Razorpay (Prepaid)", table_body_bold), Paragraph("<font color='#065F46'><b>[ Emerald Pill: Prepaid (Razorpay) ]</b></font>", table_body), Paragraph("Instant payment via UPI (GPay, PhonePe, Paytm), Credit/Debit Cards, Net Banking.", table_body)],
        [Paragraph("PayPal (Prepaid)", table_body_bold), Paragraph("<font color='#1E40AF'><b>[ Blue Pill: Prepaid (PayPal) ]</b></font>", table_body), Paragraph("International currency payments captured via PayPal REST API.", table_body)],
    ]
    pbt = Table(pay_badge_table_data, colWidths=[130, 165, 220])
    pbt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(pbt)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: LOGISTICS & 5-STAGE TRACKING LIFECYCLE
    # =========================================================================
    story.append(Paragraph("4. End-to-End Logistics & 5-Stage Live Order Tracking", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "Logistics transparency is a cornerstone of The Saveur's customer trust. The platform features an automated, multi-courier fulfillment workflow that synchronizes administrative operations with real-time customer tracking.",
        body_style
    ))

    stages_data = [
        [Paragraph("Stage", table_header), Paragraph("Status Name", table_header), Paragraph("Trigger & Operational Workflow", table_header), Paragraph("Customer Visibility & UI State", table_header)],
        [Paragraph("1", table_body_bold), Paragraph("Order Confirmed", table_body_bold), Paragraph("Triggered immediately upon successful payment or COD placement. Order received in kitchen/warehouse queue.", table_body), Paragraph("Stage 1 marked Completed with green checkmark. Customer receives immediate confirmation email.", table_body)],
        [Paragraph("2", table_body_bold), Paragraph("Shipped", table_body_bold), Paragraph("Admin enters Courier Partner & AWB tracking number. System automatically promotes status to Shipped.", table_body), Paragraph("Stage 2 marked Completed. Customer receives dispatch email with clickable AWB live tracking link.", table_body)],
        [Paragraph("3", table_body_bold), Paragraph("In Transit", table_body_bold), Paragraph("Package is en route between logistics distribution hubs and sorting centers.", table_body), Paragraph("Stage 3 marked In Progress / Completed. Stepper updates dynamically.", table_body)],
        [Paragraph("4", table_body_bold), Paragraph("Out for Delivery", table_body_bold), Paragraph("Package assigned to last-mile delivery agent for same-day handover.", table_body), Paragraph("Stage 4 highlighted. Customer receives 'Out for Delivery' heads-up email alert.", table_body)],
        [Paragraph("5", table_body_bold), Paragraph("Delivered", table_body_bold), Paragraph("Package handed over to customer. Admin marks order as Delivered.", table_body), Paragraph("All 5 stages marked Completed with green checkmarks. Delivery confirmation email sent.", table_body)],
    ]
    stg_table = Table(stages_data, colWidths=[25, 85, 205, 200])
    stg_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(stg_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Supported Courier Partners & Dynamic Tracking:", h2_style))
    courier_list = [
        [Paragraph("<b>Blue Dart:</b> <code>bluedart.com/tracking?track={awb}</code>", table_body), Paragraph("<b>Delhivery:</b> <code>delhivery.com/track/package/{awb}</code>", table_body)],
        [Paragraph("<b>DTDC:</b> <code>dtdc.in/tracking/shipment-tracking.asp?trk={awb}</code>", table_body), Paragraph("<b>India Post:</b> <code>indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx</code>", table_body)],
        [Paragraph("<b>Shadowfax:</b> <code>shadowfax.in/track?awb={awb}</code>", table_body), Paragraph("<b>Xpressbees:</b> <code>xpressbees.com/track?isawb=true&trackid={awb}</code>", table_body)],
        [Paragraph("<b>Ekart Logistics:</b> <code>ekartlogistics.com/shipmenttrack/{awb}</code>", table_body), Paragraph("<b>Ecom Express:</b> <code>ecomexpress.in/tracking/?awb={awb}</code>", table_body)],
    ]
    c_table = Table(courier_list, colWidths=[255, 260])
    c_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(c_table)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: INVOICING & REGULATORY COMPLIANCE
    # =========================================================================
    story.append(Paragraph("5. Automated Single-Page Invoicing & Tax Compliance", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The invoicing engine generates compliant, beautiful, single-page A4 tax receipts for every order. It is accessible both from the customer dashboard and the administrative console.",
        body_style
    ))

    invoice_features = [
        [Paragraph("Compliance / Design Standard", table_header), Paragraph("Implementation Specification & Detail", table_header)],
        [Paragraph("Strict Single-Page Guarantee", table_body_bold), Paragraph("Engineered with CSS <code>@media print</code> rules, compact margins, and clean flexbox rows ensuring zero page overflow or awkward 2nd page spills.", table_body)],
        [Paragraph("FSSAI Registration Display", table_body_bold), Paragraph("Prominently features standardized <b>'FSSAI No.'</b> branding, license number, and statutory food safety compliance marks.", table_body)],
        [Paragraph("GST & Tax Breakdown", table_body_bold), Paragraph("Itemizes product pricing, applied promotional discounts, state shipping charges, and inclusive GST calculation breakdown.", table_body)],
        [Paragraph("Payment Method Highlighting", table_body_bold), Paragraph("Displays color-coded badges for payment modes: <b>Cash on Delivery (Amber)</b>, <b>Prepaid Online / Razorpay (Emerald)</b>, <b>PayPal (Blue)</b>.", table_body)],
        [Paragraph("Cryptographic QR Verification", table_body_bold), Paragraph("Includes a dynamic QR code encoding the secure order access URL for rapid mobile scan-to-verify authenticity.", table_body)],
    ]
    inv_table = Table(invoice_features, colWidths=[175, 340])
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(inv_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Invoice Layout Structure Breakdown:", h2_style))
    story.append(Paragraph("&bull; <b>Header Section:</b> The Saveur brand logo, Tax Invoice title, Official FSSAI No., GSTIN, and Registered Corporate Address.", bullet_style))
    story.append(Paragraph("&bull; <b>Metadata Strip:</b> Order Reference Number (e.g. <code>TSV-A3X9KZ2Q</code>), Invoice Date, Payment Status Badge, and Highlighted Payment Mode Badge.", bullet_style))
    story.append(Paragraph("&bull; <b>Billed To &amp; Shipped To:</b> Customer full name, shipping address, city, state, postal PIN code, and contact phone number.", bullet_style))
    story.append(Paragraph("&bull; <b>Itemized Products Table:</b> S.No, Item Description, Unit Specification (e.g. 85g Jar), Unit Price, Quantity, and Line Item Total.", bullet_style))
    story.append(Paragraph("&bull; <b>Financial Summary:</b> Subtotal, Item-level Discounts, Applied Coupon Code savings, State Shipping & Logistics fee, Inclusive GST, and Final Total.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 7: TRANSACTIONAL EMAIL SYSTEM
    # =========================================================================
    story.append(Paragraph("6. Transactional Email System & Notification Dispatch", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "Customer communications follow strict enterprise design standards. All informal emojis have been eliminated in favor of clean typography, structured data cards, and secure action buttons.",
        body_style
    ))

    email_types = [
        [Paragraph("Email Event", table_header), Paragraph("Subject Line Standard", table_header), Paragraph("Key Content & Call-to-Action", table_header)],
        [Paragraph("Order Confirmed", table_body_bold), Paragraph("Order Confirmed: {order_number} - The Saveur", table_body), Paragraph("Order summary, itemized price breakdown, delivery address, highlighted payment mode, and 'Track Your Order' button.", table_body)],
        [Paragraph("Order Shipped", table_body_bold), Paragraph("Your Order {order_number} Has Been Shipped - The Saveur", table_body), Paragraph("Courier Partner name, AWB Tracking number, estimated delivery date, and direct link to carrier tracking.", table_body)],
        [Paragraph("Out for Delivery", table_body_bold), Paragraph("Out for Delivery: Order {order_number} - The Saveur", table_body), Paragraph("Same-day delivery heads-up alert, courier contact info, and recipient preparation guidelines.", table_body)],
        [Paragraph("Order Delivered", table_body_bold), Paragraph("Delivered: Order {order_number} - The Saveur", table_body), Paragraph("Handover confirmation, single-page tax invoice access link, and customer feedback invitation.", table_body)],
        [Paragraph("Account Security", table_body_bold), Paragraph("Your Verification Code / Password Reset - The Saveur", table_body), Paragraph("6-digit cryptographic OTP, 10-minute expiry warning, and unauthorized access advisory.", table_body)],
    ]
    email_table = Table(email_types, colWidths=[105, 175, 235])
    email_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(email_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Email Engineering Standards:", h2_style))
    story.append(Paragraph("&bull; <b>100% Emoji-Free Policy:</b> Clean, high-trust text layout matching Fortune 500 corporate communications.", bullet_style))
    story.append(Paragraph("&bull; <b>Cryptographic Link Authentication:</b> All action buttons (e.g. <i>Track Order</i>, <i>Download Invoice</i>) contain signed HMAC tokens allowing instant, password-free view for the genuine recipient while maintaining zero risk to their account credentials.", bullet_style))
    story.append(Paragraph("&bull; <b>Asynchronous Task Dispatch:</b> Celery workers deliver emails in the background; customer orders are confirmed in under 150 milliseconds.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 8: SECURITY & CRYPTOGRAPHY
    # =========================================================================
    story.append(Paragraph("7. Security Framework, Cryptographic Tokens & Authorization", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The Saveur implements a multi-layered security architecture protecting customer privacy, payment data, and administrative functionality against common web vulnerabilities.",
        body_style
    ))

    sec_data = [
        [Paragraph("Security Layer", table_header), Paragraph("Mechanism & Standard", table_header), Paragraph("Protection Objective", table_header)],
        [Paragraph("Secure Alphanumeric IDs", table_body_bold), Paragraph("Replaced sequential database IDs with <code>TSV-XXXXXXXX</code> references.", table_body), Paragraph("Prevents competitor order-volume scraping and sequential guessing attacks.", table_body)],
        [Paragraph("HMAC-SHA256 Tokenization", table_body_bold), Paragraph("Cryptographically signed tokens embedded in email direct-links: <code>?token=...</code>", table_body), Paragraph("Allows seamless one-click tracking/invoice viewing from email without exposing login sessions.", table_body)],
        [Paragraph("Customer Ownership Auth", table_body_bold), Paragraph("Strict session-to-order binding (<code>session['user_id'] == order['user_id']</code>).", table_body), Paragraph("Completely prevents Insecure Direct Object References (IDOR).", table_body)],
        [Paragraph("Payment Signature Verification", table_body_bold), Paragraph("Razorpay HMAC-SHA256 signature verification & PayPal REST OAuth capture.", table_body), Paragraph("Prevents fraudulent checkout injection, spoofed amounts, and unpaid order approvals.", table_body)],
        [Paragraph("Password & Session Security", table_body_bold), Paragraph("PBKDF2 SHA-256 password hashing with salt, HTTPOnly cookies, CSRF defenses.", table_body), Paragraph("Guarantees credential safety and prevents session hijacking.", table_body)],
    ]
    sec_table = Table(sec_data, colWidths=[120, 185, 210])
    sec_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(sec_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Cryptographic Access Verification Flow:", h2_style))
    story.append(Paragraph("When an order tracking or invoice URL is requested (e.g. <code>/track-order/TSV-A3X9KZ2Q</code>):", body_style))
    story.append(Paragraph("1. If an Admin session is active, full operational access is granted immediately.", bullet_style))
    story.append(Paragraph("2. If a Customer session is active, the system checks if <code>session['user_id'] == order['user_id']</code>. If matched, access is granted; if mismatched, access is blocked.", bullet_style))
    story.append(Paragraph("3. If no session is active (e.g., opened directly from customer email), the system evaluates the <code>?token=</code> query parameter against the HMAC-SHA256 signature generated with the server secret key. If valid, secure read-only access is granted.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 9: ADMIN CONTROL PORTAL
    # =========================================================================
    story.append(Paragraph("8. Administrative Control Portal & Operations Manual", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The administrative panel (<code>/admin</code>) provides business operators with a centralized, intuitive command center to oversee orders, catalog inventory, shipping rates, promotional campaigns, and customer service inquiries.",
        body_style
    ))

    admin_modules = [
        [Paragraph("Module", table_header), Paragraph("URL Route", table_header), Paragraph("Key Capabilities & Operations", table_header)],
        [Paragraph("Executive Dashboard", table_body_bold), Paragraph("<code>/admin</code>", table_body), Paragraph("Live revenue metrics, today's order counts, low-stock alerts, recent customer transactions, and order distribution graphs.", table_body)],
        [Paragraph("Order Fulfillment", table_body_bold), Paragraph("<code>/admin/orders</code>", table_body), Paragraph("Search & filter orders by status, view customer profile & delivery coordinates, assign Courier Partner & AWB number, print tax invoices.", table_body)],
        [Paragraph("Product Catalog", table_body_bold), Paragraph("<code>/admin/products</code>", table_body), Paragraph("Add/Edit/Delete products, manage unit weights, upload primary & secondary gallery images, adjust stock counts, toggle Bestseller tags.", table_body)],
        [Paragraph("Categories & Taxonomy", table_body_bold), Paragraph("<code>/admin/categories</code>", table_body), Paragraph("Create top-level food categories (e.g. Makhana, Dry Fruits, Cookies) and nested subcategories with image banners.", table_body)],
        [Paragraph("Couriers & Logistics", table_body_bold), Paragraph("<code>/admin/couriers</code>", table_body), Paragraph("Add new courier carriers, define live tracking URL templates with <code>{awb}</code> placeholders, manage carrier statuses.", table_body)],
        [Paragraph("Shipping Rates Engine", table_body_bold), Paragraph("<code>/admin/shipping</code>", table_body), Paragraph("Configure state-specific shipping charges across all 36 Indian States & Union Territories.", table_body)],
        [Paragraph("Promos & Coupons", table_body_bold), Paragraph("<code>/admin/promos</code>", table_body), Paragraph("Create percentage or flat discount coupon codes, set minimum order values, define usage limits and expiry dates.", table_body)],
        [Paragraph("Hero Banner Slides", table_body_bold), Paragraph("<code>/admin/slides</code>", table_body), Paragraph("Manage homepage carousel imagery, marketing headlines, subheadings, and direct call-to-action button links.", table_body)],
        [Paragraph("Customer Enquiries", table_body_bold), Paragraph("<code>/admin/enquiries</code>", table_body), Paragraph("Review customer contact messages, bulk corporate gifting inquiries, and direct reply records.", table_body)],
        [Paragraph("System Diagnostics", table_body_bold), Paragraph("<code>/admin/system</code>", table_body), Paragraph("Clear Redis cache, inspect Celery queue depth, monitor database size, view error logs.", table_body)],
    ]
    adm_table = Table(admin_modules, colWidths=[95, 115, 305])
    adm_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(adm_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Order Fulfillment Guide:", h2_style))
    story.append(Paragraph("1. Open the order in <b>Admin &rarr; Orders &rarr; View Order</b>.", bullet_style))
    story.append(Paragraph("2. Review items and pack package with packing slip.", bullet_style))
    story.append(Paragraph("3. Select <b>Courier Partner</b> and paste the <b>AWB / Tracking Number</b> in the logistics card.", bullet_style))
    story.append(Paragraph("4. Click <b>Save</b>. The order status automatically transitions to <b>Shipped</b> and customer is notified via email with live tracking link.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 10: DATABASE SCHEMA & ENTITIES
    # =========================================================================
    story.append(Paragraph("9. Database Relational Schema & Entity Specifications", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The relational database contains 14 structured tables maintaining foreign key integrity and indexing on critical lookup columns (e.g. <code>order_number</code>, <code>email</code>, <code>category</code>).",
        body_style
    ))

    db_tables = [
        [Paragraph("Table Name", table_header), Paragraph("Primary Key", table_header), Paragraph("Key Columns & Relationships", table_header)],
        [Paragraph("<code>users</code>", table_body_bold), Paragraph("<code>id</code> (TEXT)", table_body), Paragraph("<code>full_name, email (UNIQUE), password_hash, is_admin, phone, shipping_address, city, state, zip_code, created_at</code>", table_body)],
        [Paragraph("<code>products</code>", table_body_bold), Paragraph("<code>id</code> (TEXT)", table_body), Paragraph("<code>name, category, sub_category, description, image_filename, price, stocks, is_bestseller, unit, shipping_charge, gst_rate, discount_percent</code>", table_body)],
        [Paragraph("<code>product_images</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>product_id (FK &rarr; products.id), image_filename, is_primary, display_order</code>", table_body)],
        [Paragraph("<code>categories</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>name (UNIQUE), image_filename, display_order</code>", table_body)],
        [Paragraph("<code>subcategories</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>category_id (FK &rarr; categories.id), name, display_order</code>", table_body)],
        [Paragraph("<code>orders</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>user_id (FK &rarr; users.id), order_number (UNIQUE), total_amount, shipping_address, city, state, zip_code, payment_method, status, contact_name, contact_email, contact_phone, courier_partner, tracking_number, estimated_delivery, razorpay_order_id, razorpay_payment_id, paypal_order_id, discount_amount, promo_code, shipping_charge, created_at</code>", table_body)],
        [Paragraph("<code>order_items</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>order_id (FK &rarr; orders.id), product_id (FK &rarr; products.id), quantity, price, original_price, discount_percent</code>", table_body)],
        [Paragraph("<code>location_shipping_charges</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>state (UNIQUE), charge</code>", table_body)],
        [Paragraph("<code>couriers</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>name (UNIQUE), tracking_url_template, is_active, display_order</code>", table_body)],
        [Paragraph("<code>promo_codes</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>code (UNIQUE), discount_percent, flat_discount, min_order_amount, max_discount, valid_until, is_active</code>", table_body)],
        [Paragraph("<code>carousel_slides</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>title, subtitle, button_text, button_link, image_filename, display_order, is_active</code>", table_body)],
        [Paragraph("<code>reviews</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>product_id (FK &rarr; products.id), user_id (FK &rarr; users.id), rating, review_text, created_at</code>", table_body)],
        [Paragraph("<code>enquiries</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>name, email, phone, subject, message, created_at</code>", table_body)],
        [Paragraph("<code>password_resets</code>", table_body_bold), Paragraph("<code>id</code> (INTEGER)", table_body), Paragraph("<code>email, otp_hash, expires_at, used</code>", table_body)],
    ]
    dbt_table = Table(db_tables, colWidths=[100, 75, 340])
    dbt_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(dbt_table)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 11: API DIRECTORY & ROUTING
    # =========================================================================
    story.append(Paragraph("10. API Directory, Routing Architecture & Endpoints", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "The system exposes a clean RESTful URL hierarchy mapped to modular Flask Blueprints:",
        body_style
    ))

    routes_data = [
        [Paragraph("Endpoint Pattern", table_header), Paragraph("HTTP Method", table_header), Paragraph("Blueprint / Handler", table_header), Paragraph("Description & Access Level", table_header)],
        [Paragraph("<code>/</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>storefront.index</code>", table_body), Paragraph("Homepage with hero slides, categories, and bestsellers.", table_body)],
        [Paragraph("<code>/shop</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>products.shop</code>", table_body), Paragraph("Catalog with price/category/subcategory filters.", table_body)],
        [Paragraph("<code>/product/&lt;id&gt;</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>products.product_detail</code>", table_body), Paragraph("Product detail view, image gallery, specs & reviews.", table_body)],
        [Paragraph("<code>/cart</code>", table_body_bold), Paragraph("GET/POST", table_body), Paragraph("<code>cart.view_cart</code>", table_body), Paragraph("Cart management, item updates, promo application.", table_body)],
        [Paragraph("<code>/checkout</code>", table_body_bold), Paragraph("GET/POST", table_body), Paragraph("<code>checkout.checkout_step1</code>", table_body), Paragraph("Shipping address capture & state shipping calculation.", table_body)],
        [Paragraph("<code>/checkout/payment</code>", table_body_bold), Paragraph("GET/POST", table_body), Paragraph("<code>checkout.checkout_step2</code>", table_body), Paragraph("Payment selection, Razorpay order creation, PayPal capture.", table_body)],
        [Paragraph("<code>/track-order/&lt;order_ref&gt;</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>orders.track_order</code>", table_body), Paragraph("Secure live tracking page (HMAC / User auth).", table_body)],
        [Paragraph("<code>/orders/&lt;order_ref&gt;/invoice</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>orders.order_invoice</code>", table_body), Paragraph("Customer single-page tax invoice print/view.", table_body)],
        [Paragraph("<code>/my-orders</code>", table_body_bold), Paragraph("GET", table_body), Paragraph("<code>orders.my_orders</code>", table_body), Paragraph("Customer account order history with status pills.", table_body)],
        [Paragraph("<code>/login, /register, /logout</code>", table_body_bold), Paragraph("GET/POST", table_body), Paragraph("<code>auth.*</code>", table_body), Paragraph("Customer authentication and session management.", table_body)],
        [Paragraph("<code>/admin/*</code>", table_body_bold), Paragraph("GET/POST", table_body), Paragraph("<code>admin.*</code>", table_body), Paragraph("Admin management suites (Admin role required).", table_body)],
    ]
    r_table = Table(routes_data, colWidths=[150, 60, 110, 195])
    r_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(r_table)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 12: DEPLOYMENT & MAINTENANCE
    # =========================================================================
    story.append(Paragraph("11. Deployment, Environment Variables & Maintenance Guide", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph("Key Environment Configuration Variables (<code>.env</code>):", h2_style))
    env_vars = [
        [Paragraph("Variable Name", table_header), Paragraph("Default / Example", table_header), Paragraph("Purpose & Operational Requirement", table_header)],
        [Paragraph("<code>SECRET_KEY</code>", table_body_bold), Paragraph("<code>hex_string_64_bytes</code>", table_body), Paragraph("Cryptographic signing key for sessions, cookies, and HMAC order access tokens.", table_body)],
        [Paragraph("<code>DATABASE_URL</code>", table_body_bold), Paragraph("<code>sqlite:///thesaveur.db</code>", table_body), Paragraph("Connection string for SQLite database or remote PostgreSQL cluster.", table_body)],
        [Paragraph("<code>REDIS_URL</code>", table_body_bold), Paragraph("<code>redis://localhost:6379/0</code>", table_body), Paragraph("Cache broker URL for taxonomy and catalog acceleration.", table_body)],
        [Paragraph("<code>CELERY_BROKER_URL</code>", table_body_bold), Paragraph("<code>amqp://guest:guest@localhost:5672//</code>", table_body), Paragraph("RabbitMQ message broker URL for asynchronous task dispatch.", table_body)],
        [Paragraph("<code>RAZORPAY_KEY_ID / SECRET</code>", table_body_bold), Paragraph("<code>rzp_live_... / sec_...</code>", table_body), Paragraph("Live API keys for domestic UPI, cards, and netbanking processing.", table_body)],
        [Paragraph("<code>PAYPAL_CLIENT_ID / SECRET</code>", table_body_bold), Paragraph("<code>client_... / secret_...</code>", table_body), Paragraph("REST API credentials for international multi-currency checkout.", table_body)],
        [Paragraph("<code>MAIL_SERVER / USER / PASSWORD</code>", table_body_bold), Paragraph("<code>smtp.hostinger.com:465</code>", table_body), Paragraph("SSL/TLS SMTP server credentials for transactional email delivery.", table_body)],
    ]
    e_table = Table(env_vars, colWidths=[145, 125, 245])
    e_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(e_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Routine Maintenance & Backup Instructions:", h2_style))
    story.append(Paragraph("&bull; <b>Database Backups:</b> The SQLite database file <code>thesaveur.db</code> should be backed up daily via cron to secure cloud storage (AWS S3 / Google Cloud Storage).", bullet_style))
    story.append(Paragraph("&bull; <b>Media Asset Storage:</b> All uploaded product photos and carousel banners are persisted under <code>static/images/products/</code> and <code>static/images/carousel/</code>.", bullet_style))
    story.append(Paragraph("&bull; <b>One-Command Production Deployment:</b> Use <code>./deploy.sh</code> to perform git pulls, dependency updates, and zero-downtime Gunicorn worker restarts on Linux servers.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 13: DELIVERABLES & SIGN-OFF
    # =========================================================================
    story.append(Paragraph("12. Client Deliverables Sign-Off & Handover", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=8))

    story.append(Paragraph(
        "All requested business requirements, UI improvements, logistics integrations, and security hardening have been implemented, tested, and validated against production standards.",
        body_style
    ))

    deliv_data = [
        [Paragraph("Feature / Deliverable", table_header), Paragraph("Scope Delivered", table_header), Paragraph("Verification Status", table_header)],
        [Paragraph("Single-Page Tax Invoicing", table_body_bold), Paragraph("Compact CSS print rules, FSSAI No. compliance, GST breakdown, QR verification.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("5-Stage Logistics Stepper", table_body_bold), Paragraph("Order Confirmed &rarr; Shipped &rarr; In Transit &rarr; Out for Delivery &rarr; Delivered.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("Dynamic Multi-Courier Integration", table_body_bold), Paragraph("Auto-promotes to Shipped upon AWB input; generates direct carrier links.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("Alphanumeric Secure Order URLs", table_body_bold), Paragraph("Customer & Admin URLs use non-guessable <code>TSV-XXXXXXXX</code> references.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("Cryptographic Email Access (HMAC)", table_body_bold), Paragraph("Passwordless direct-access tokens in transactional email buttons.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("IDOR Customer Ownership Protection", table_body_bold), Paragraph("Blocks unauthorized cross-customer tracking or invoice access.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("De-emojified Transactional Emails", table_body_bold), Paragraph("Clean, professional enterprise email cards for all 4 key lifecycle stages.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
        [Paragraph("Highlighted Payment Method Badges", table_body_bold), Paragraph("Color-coded COD, Prepaid (Razorpay), PayPal pills across Admin, Customer & Invoice.", table_body), Paragraph("VERIFIED (100%)", table_body_bold)],
    ]
    d_table = Table(deliv_data, colWidths=[150, 260, 105])
    d_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(d_table)
    story.append(Spacer(1, 20))

    # Handover Signatures Table
    sig_data = [
        [Paragraph("<b>Prepared By (Engineering Lead):</b>", table_body), Paragraph("<b>Accepted & Approved By (Client):</b>", table_body)],
        [Paragraph("<br/><br/>________________________________________<br/>Lead Software Engineer<br/>The Saveur Core Team", table_body),
         Paragraph("<br/><br/>________________________________________<br/>Authorized Signatory<br/>The Saveur Gourmet Foods", table_body)],
        [Paragraph("Date: September 5, 2026", table_body), Paragraph("Date: ________________________", table_body)]
    ]
    sig_table = Table(sig_data, colWidths=[255, 260])
    sig_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(sig_table)

    # Build Document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF Successfully generated: {filename}")


if __name__ == '__main__':
    output_filename = "The_Saveur_Complete_Client_Documentation.pdf"
    if len(sys.argv) > 1:
        output_filename = sys.argv[1]
    build_pdf(output_filename)
