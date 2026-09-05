import os
import smtplib
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate, make_msgid, formataddr, parseaddr
from flask import request, has_request_context
from database import get_db
from services.couriers_service import generate_tracking_url, get_courier_metadata
from services.email_templates import get_email_template
from services.auth_service import generate_order_access_token


def _strip_html(html_str):
    """Simple helper to create a clean plain-text fallback from HTML."""
    clean = re.sub(r'<[^>]+>', ' ', html_str)
    return re.sub(r'\s+', ' ', clean).strip()


def _get_smtp_credentials():
    """Retrieve and sanitize SMTP credentials."""
    smtp_host = os.environ.get('SMTP_HOST') or os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = os.environ.get('SMTP_PORT', '587')
    smtp_user = os.environ.get('SMTP_USER', '').strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()
    raw_sender = os.environ.get('SMTP_SENDER', smtp_user).strip()

    parsed_name, parsed_email = parseaddr(raw_sender)
    sender_email = parsed_email if parsed_email else (smtp_user if smtp_user else raw_sender)
    sender_name = parsed_name if parsed_name else "The Saveur"

    return smtp_host, smtp_port, smtp_user, smtp_password, sender_email, sender_name


def _build_smtp_headers(msg, subject, receiver_email, sender_email, sender_name):
    """Set standard RFC-compliant email headers to maximize inbox delivery."""
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = receiver_email
    msg['Reply-To'] = sender_email
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='thesaveur.com')
    msg['Auto-Submitted'] = 'auto-generated'
    msg['X-Auto-Response-Suppress'] = 'All'


def send_custom_html_email(receiver_email, subject, html_body, plain_body=None):
    """General custom HTML email sending function via SMTP with plain-text fallback."""
    smtp_host, smtp_port, smtp_user, smtp_password, sender_email, sender_name = _get_smtp_credentials()

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, sender_email]):
        print(f"[SMTP] SMTP variables not fully set. Skip sending '{subject}'.")
        return False

    try:
        port = int(smtp_port)
        msg = MIMEMultipart('alternative')
        _build_smtp_headers(msg, subject, receiver_email, sender_email, sender_name)
        
        # 1. Plain text fallback (reduces spam score)
        text_content = plain_body or _strip_html(html_body)
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        
        # 2. Rich HTML part
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if port == 465:
            server = smtplib.SMTP_SSL(smtp_host, port, timeout=10)
            server.login(smtp_user, smtp_password)
        else:
            server = smtplib.SMTP(smtp_host, port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_password)

        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print(f"[SMTP] Successfully sent custom email '{subject}' to {receiver_email}")
        return True
    except Exception as e:
        print(f"[SMTP] Failed to send custom email to {receiver_email}: {str(e)}")
        return False


def send_otp_email(receiver_email, otp, purpose='reset'):
    """Dispatch OTP email for verification or password reset with high inbox deliverability."""
    print(f"[OTP DISPATCH] Generated {purpose} OTP for {receiver_email}: {otp}")

    smtp_host, smtp_port, smtp_user, smtp_password, sender_email, sender_name = _get_smtp_credentials()

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, sender_email]):
        print(f"[SMTP] Not fully configured. (Required: SMTP_HOST/SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD). Local OTP is: {otp}")
        return False

    if purpose == 'signup':
        subject = f"{otp} is your verification code – The Saveur"
        heading = "Verify Your Email Address"
        body_text = ("You're almost there! Enter the 6-digit code below to verify your email address "
                     "and complete your account registration. This OTP is valid for 10 minutes.")
    elif purpose == 'admin_login':
        subject = f"{otp} is your admin login code – The Saveur"
        heading = "Admin Login Verification"
        body_text = ("An administrator login attempt was detected for your account. Enter the 6-digit code "
                     "below to verify your identity and complete the login. This OTP is valid for 10 minutes.")
    else:
        subject = f"{otp} is your password reset code – The Saveur"
        heading = "Password Reset Request"
        body_text = ("We received a request to reset your password. Use the verification code below "
                     "to proceed with the password reset process. This OTP is valid for 10 minutes.")

    plain_text = f"""Hello,

{body_text}

Your Verification Code: {otp}

(This code will expire in 10 minutes. Please do not share this OTP with anyone.)

If you did not request this code, you can safely ignore this email.

— The Saveur Team
https://thesaveur.com
"""

    try:
        port = int(smtp_port)
        msg = MIMEMultipart('alternative')
        _build_smtp_headers(msg, subject, receiver_email, sender_email, sender_name)
        msg['X-Priority'] = '1'
        
        msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        
        body_content = f"""
        <p style="color: #3d3d3d; font-size: 15px; margin-top: 0;">Hello,</p>
        <p style="color: #3d3d3d; font-size: 15px; line-height: 1.6;">{body_text}</p>
        
        <div style="background-color: #FAF7F2; border: 1.5px dashed #C8860A; border-radius: 8px; padding: 20px; text-align: center; margin: 28px 0;">
            <div style="font-size: 12px; color: #777777; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;">One-Time Password</div>
            <span style="font-size: 34px; font-weight: 700; letter-spacing: 8px; color: #C8860A; font-family: monospace;">{otp}</span>
        </div>
        
        <p style="color: #6b6b6b; font-size: 13px; margin-bottom: 6px;">&bull; This code is valid for <strong>10 minutes</strong>.</p>
        <p style="color: #6b6b6b; font-size: 13px; margin-top: 0;">&bull; For security reasons, never share this code with anyone.</p>
        """
        
        html_body = get_email_template(heading, body_content, footer_note="This code was requested for security verification on The Saveur. Never share your OTP with anyone.")
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if port == 465:
            server = smtplib.SMTP_SSL(smtp_host, port, timeout=10)
            server.login(smtp_user, smtp_password)
        else:
            server = smtplib.SMTP(smtp_host, port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_password)

        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print(f"[SMTP] Successfully sent {purpose} OTP email to {receiver_email}")
        return True

    except Exception as e:
        print(f"[SMTP ERROR] Failed to send {purpose} email to {receiver_email}: {str(e)}")
        print(f"[OTP BACKUP] Use this OTP to verify {receiver_email}: {otp}")
        return False


def send_login_alert_email(user_email, user_name):
    """Notify user of a new login."""
    subject = "Security Alert: New Login – The Saveur"
    time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px;">Your account logged in successfully at <strong>{time_str}</strong>.</p>
    <p style="color: #3d3d3d; font-size: 15px;">If this was you, no action is required. If you did not log in, please reset your password immediately or contact support.</p>
    """
    html_body = get_email_template("Security Alert: New Login", body_content)
    send_custom_html_email(user_email, subject, html_body)


def _render_email_tracking_stepper(current_status):
    """
    Render a 5-stage tracking progress bar for email clients:
    Order Confirmed -> Shipped -> In Transit -> Out for Delivery -> Delivered
    """
    stages = [
        ('Order Confirmed', 'Confirmed'),
        ('Shipped', 'Shipped'),
        ('In Transit', 'In Transit'),
        ('Out for Delivery', 'Out for Delivery'),
        ('Delivered', 'Delivered')
    ]
    status_ranks = {
        'Order Confirmed': 1,
        'Processing': 1,
        'Placed': 1,
        'Shipped': 2,
        'In Transit': 3,
        'Out for Delivery': 4,
        'Delivered': 5
    }
    cur_rank = status_ranks.get(current_status, 1)

    cells = []
    for idx, (stage_key, label) in enumerate(stages, 1):
        if idx < cur_rank:
            color = "#059669"
            bg = "#ecfdf5"
            border = "#a7f3d0"
            dot = "✓"
        elif idx == cur_rank:
            color = "#ffffff"
            bg = "#059669"
            border = "#059669"
            dot = str(idx)
        else:
            color = "#94a3b8"
            bg = "#f8fafc"
            border = "#e2e8f0"
            dot = str(idx)

        cells.append(f"""
        <td style="width: 20%; padding: 4px 2px; text-align: center; vertical-align: top;">
            <div style="display: inline-block; width: 22px; height: 22px; line-height: 20px; border-radius: 50%; background: {bg}; border: 1.5px solid {border}; color: {color}; font-size: 11px; font-weight: 700; margin-bottom: 4px;">
                {dot}
            </div>
            <div style="font-size: 10px; font-weight: 700; color: {'#065f46' if idx <= cur_rank else '#94a3b8'}; line-height: 1.2;">
                {label}
            </div>
        </td>
        """)

    stepper_html = f"""
    <div style="background: #fafaf9; border: 1px solid #e7e5e4; border-radius: 10px; padding: 14px 6px; margin: 18px 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
            <tr>
                {"".join(cells)}
            </tr>
        </table>
    </div>
    """
    return stepper_html


# ══════════════════════════════════════════════════════════════════════
# 1. ORDER CONFIRMED EMAIL
# ══════════════════════════════════════════════════════════════════════
def send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items):
    """Send order booking confirmation with 5-stage progress indicator and invoice summary."""
    subject = f"Order Confirmed – #{order_number} | The Saveur"
    stepper_html = _render_email_tracking_stepper('Order Confirmed')

    items_rows = ""
    for item in items:
        subtotal = item['quantity'] * item['price']
        items_rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee;">{item['product_name']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: center;">{item['quantity']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">${item['price']:.2f}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">${subtotal:.2f}</td>
        </tr>
        """
    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">Thank you for shopping with The Saveur! Your order <strong>#{order_number}</strong> has been confirmed and is being carefully packed for shipment.</p>
    
    {stepper_html}

    <div style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin: 16px 0; text-align: center;">
        <span style="font-size: 13px; font-weight: 700; color: #166534;">Status: Order Confirmed</span>
        <div style="font-size: 12px; color: #15803d; margin-top: 2px;">We will send you a tracking email with the courier details as soon as your order is dispatched.</div>
    </div>

    <h3 style="color: #2D5016; border-bottom: 2px solid #2D5016; padding-bottom: 6px; margin-top: 20px; font-size: 15px;">Order Summary</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
        <thead>
            <tr style="background-color: #FAF7F2; color: #2D5016; font-weight: bold;">
                <th style="padding: 8px; text-align: left;">Item</th>
                <th style="padding: 8px; text-align: center;">Qty</th>
                <th style="padding: 8px; text-align: right;">Price</th>
                <th style="padding: 8px; text-align: right;">Total</th>
            </tr>
        </thead>
        <tbody>
            {items_rows}
        </tbody>
    </table>
    
    <div style="margin-top: 14px; text-align: right; font-size: 15px; font-weight: bold; color: #2D5016;">
        Total Amount: ${total_amount:.2f}
    </div>
    
    <div style="background-color: #FAF7F2; border-radius: 8px; padding: 12px 14px; margin-top: 18px;">
        <strong style="color: #2D5016; font-size: 12px; text-transform: uppercase;">Shipping Address:</strong><br>
        <span style="font-size: 13px; color: #3d3d3d; line-height: 1.4;">{shipping_address}</span>
    </div>
    """
    html_body = get_email_template("Your Order is Confirmed", body_content, footer_note="Thank you for ordering from The Saveur.")
    send_custom_html_email(user_email, subject, html_body)


# ══════════════════════════════════════════════════════════════════════
# 2 & 3. SHIPPED & OUT FOR DELIVERY & IN TRANSIT TRACKING EMAILS
# ══════════════════════════════════════════════════════════════════════
def send_order_tracking_email(user_email, user_name, order_number, status, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    """
    Notify customer with real-time tracking details, 5-stage progress indicator,
    courier name, AWB ID, EDD, and live tracking links.
    Handles 'Shipped', 'In Transit', and 'Out for Delivery'.
    """
    courier_meta = get_courier_metadata(courier_partner) if courier_partner else None
    courier_display = courier_meta['name'] if courier_meta else (courier_partner or 'Express Courier Partner')

    status_titles = {
        'Shipped': 'Your Order Has Been Shipped',
        'In Transit': 'Your Package is In Transit',
        'Out for Delivery': 'Your Package is Out for Delivery'
    }
    status_descriptions = {
        'Shipped': f"Great news! Your order <strong>#{order_number}</strong> has been dispatched via <strong>{courier_display}</strong> and is currently on its way to you.",
        'In Transit': f"Your package for order <strong>#{order_number}</strong> is in transit between logistics hubs with <strong>{courier_display}</strong>.",
        'Out for Delivery': f"Your package for order <strong>#{order_number}</strong> is <strong>out for delivery today</strong> with your local <strong>{courier_display}</strong> courier agent. Please ensure someone is available at the delivery address to receive it."
    }

    heading = status_titles.get(status, f"Order Tracking: {status}")
    subject = f"{heading} – #{order_number} | The Saveur"
    desc_text = status_descriptions.get(status, f"Your order #{order_number} status is now {status}.")

    stepper_html = _render_email_tracking_stepper(status)

    courier_info_html = ""
    if courier_partner or tracking_number or estimated_delivery_date:
        courier_info_html = f"""
        <div style="background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 16px 18px; margin: 18px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                <tr>
                    <td style="padding-bottom: 8px; font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;" colspan="2">
                        Shipment &amp; Courier Details
                    </td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; font-size: 13px; color: #475569; font-weight: 600;">Delivery Partner:</td>
                    <td style="padding: 4px 0; font-size: 13px; color: #0f172a; font-weight: 700; text-align: right;">{courier_display}</td>
                </tr>
                {f'''<tr>
                    <td style="padding: 4px 0; font-size: 13px; color: #475569; font-weight: 600;">Tracking / AWB Number:</td>
                    <td style="padding: 4px 0; font-size: 13px; color: #059669; font-weight: 700; font-family: monospace; text-align: right;">{tracking_number}</td>
                </tr>''' if tracking_number else ''}
                {f'''<tr>
                    <td style="padding: 4px 0; font-size: 13px; color: #475569; font-weight: 600;">Estimated Delivery:</td>
                    <td style="padding: 4px 0; font-size: 13px; color: #d97706; font-weight: 700; text-align: right;">{estimated_delivery_date}</td>
                </tr>''' if estimated_delivery_date else ''}
            </table>
        </div>
        """

    official_courier_url = generate_tracking_url(courier_partner, tracking_number) if (courier_partner and tracking_number) else None
    courier_link_html = ""
    if official_courier_url:
        courier_link_html = f"""
        <div style="margin-top: 10px;">
            <a href="{official_courier_url}" target="_blank" style="color: #059669; font-size: 12px; font-weight: 600; text-decoration: underline;">
                Track on {courier_display} Official Portal &rarr;
            </a>
        </div>
        """

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px; margin-bottom: 6px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 14px; line-height: 1.5;">{desc_text}</p>
    
    {stepper_html}
    {courier_info_html}
    
    <div style="text-align: center; margin: 24px 0 14px;">
        <a href="{tracking_url}" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 99px; font-weight: 700; font-size: 14px; box-shadow: 0 4px 12px rgba(16,185,129,0.3); display: inline-block;">
            Track Your Order
        </a>
        {courier_link_html}
    </div>
    
    <p style="color: #6b6b6b; font-size: 12px; text-align: center; line-height: 1.4;">
        Track real-time delivery checkpoints, download invoices, or contact our support team anytime.
    </p>
    """

    html_body = get_email_template(heading, body_content, footer_note="This is an automated shipping notification for your order with The Saveur.")
    send_custom_html_email(user_email, subject, html_body)


def send_order_shipped_email(user_email, user_name, order_number, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    """Alias for send_order_tracking_email for Shipped status."""
    return send_order_tracking_email(
        user_email=user_email,
        user_name=user_name,
        order_number=order_number,
        status='Shipped',
        tracking_url=tracking_url,
        courier_partner=courier_partner,
        tracking_number=tracking_number,
        estimated_delivery_date=estimated_delivery_date
    )


def send_order_out_for_delivery_email(user_email, user_name, order_number, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    """Explicit helper for Out for Delivery status email."""
    return send_order_tracking_email(
        user_email=user_email,
        user_name=user_name,
        order_number=order_number,
        status='Out for Delivery',
        tracking_url=tracking_url,
        courier_partner=courier_partner,
        tracking_number=tracking_number,
        estimated_delivery_date=estimated_delivery_date
    )


# ══════════════════════════════════════════════════════════════════════
# 4. DELIVERED EMAIL
# ══════════════════════════════════════════════════════════════════════
def send_order_delivered_email(user_email, user_name, order_number, order_id=None, user_id=None, host_url=None):
    """Notify user of successful delivery with invoice and feedback options."""
    subject = f"Your Order #{order_number} Has Been Delivered | The Saveur"
    stepper_html = _render_email_tracking_stepper('Delivered')
    
    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    token = generate_order_access_token(order_id, user_id, order_number) if (order_id and user_id) else None
    invoice_ref = order_number if order_number else order_id
    token_query = f"?token={token}" if token else ""
    invoice_url = f"{host_url.rstrip('/')}/orders/{invoice_ref}/invoice{token_query}" if invoice_ref else f"{host_url.rstrip('/')}/my-orders"

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">Your order <strong>#{order_number}</strong> has been successfully delivered. We hope you enjoy your premium products!</p>
    
    {stepper_html}

    <div style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; padding: 14px 18px; margin: 20px 0; text-align: center;">
        <span style="font-size: 14px; font-weight: 700; color: #166534;">Package Successfully Delivered</span>
        <div style="font-size: 12px; color: #15803d; margin-top: 4px;">Thank you for trusting The Saveur for pure, authentic, and natural products.</div>
    </div>

    <div style="text-align: center; margin: 24px 0 16px;">
        <a href="{invoice_url}" style="background: #2D5016; color: #ffffff; padding: 12px 26px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">
            View / Download Tax Invoice
        </a>
    </div>

    <p style="color: #666666; font-size: 13px; text-align: center; margin-top: 16px;">
        If you have any feedback or queries about your package, our support team is always ready to assist at <a href="mailto:info@thesaveur.com" style="color:#2D5016;">info@thesaveur.com</a>.
    </p>
    """
    html_body = get_email_template("Order Delivered Successfully", body_content, footer_note="Thank you for shopping with The Saveur.")
    send_custom_html_email(user_email, subject, html_body)


# ══════════════════════════════════════════════════════════════════════
# MAIN STATUS DISPATCHER
# ══════════════════════════════════════════════════════════════════════
def send_order_status_update_email(order_id, new_status, host_url=None):
    """
    Fetch order details and send appropriate email for all key lifecycle milestones:
    - Order Confirmed
    - Shipped
    - Out for Delivery (also In Transit)
    - Delivered
    - Cancelled
    """
    db = get_db()
    order = db.execute(
        """
        SELECT o.id, o.user_id, o.order_number, o.courier_partner, o.tracking_number, o.tracking_url, 
               o.estimated_delivery_date, o.total_amount, o.shipping_address, o.city, o.state, o.zip_code,
               u.full_name, u.email 
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
        """,
        (order_id,)
    ).fetchone()

    if not order:
        db.close()
        return

    user_email = order['email']
    user_name = order['full_name']
    order_number = order['order_number'] if order['order_number'] else f"#{order_id}"

    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    token = generate_order_access_token(order['id'], order['user_id'], order['order_number'] or '')
    tracking_ref = order['order_number'] if order['order_number'] else order_id
    tracking_url = f"{host_url.rstrip('/')}/track-order/{tracking_ref}?token={token}"

    if new_status in ['Order Confirmed', 'Processing', 'Placed']:
        items = db.execute(
            """
            SELECT oi.*, p.name as product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
            """,
            (order_id,)
        ).fetchall()
        db.close()
        send_order_confirmation_email(
            user_email=user_email,
            user_name=user_name,
            order_number=order_number,
            total_amount=order['total_amount'],
            shipping_address=f"{order['shipping_address']}, {order['city']}, {order['state']} – {order['zip_code']}",
            items=[dict(i) for i in items]
        )

    elif new_status in ['Shipped', 'In Transit', 'Out for Delivery']:
        db.close()
        send_order_tracking_email(
            user_email=user_email,
            user_name=user_name,
            order_number=order_number,
            status=new_status,
            tracking_url=tracking_url,
            courier_partner=order['courier_partner'],
            tracking_number=order['tracking_number'],
            estimated_delivery_date=order['estimated_delivery_date']
        )

    elif new_status == 'Delivered':
        db.close()
        send_order_delivered_email(user_email, user_name, order_number, order_id=order_id, user_id=order['user_id'], host_url=host_url)

    elif new_status == 'Cancelled':
        db.close()
        subject = f"Your Order #{order_number} has been Cancelled – The Saveur"
        body_content = f"""
        <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
        <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been cancelled. If you paid online, the refund will be initiated to your source account.</p>
        <p style="color: #3d3d3d; font-size: 15px;">If you have any questions, please contact our support team.</p>
        """
        html_body = get_email_template("Order Cancelled", body_content, banner_color_start="#e74c3c", banner_color_end="#c0392b", footer_note="Order cancellation notice from The Saveur.")
        send_custom_html_email(user_email, subject, html_body)
    else:
        db.close()


# Queue dispatchers with fallback to synchronous execution
def queue_otp_email(receiver_email, otp, purpose='reset'):
    return send_otp_email(receiver_email, otp, purpose)

def queue_login_alert_email(user_email, user_name):
    return send_login_alert_email(user_email, user_name)

def queue_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items):
    return send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items)

def queue_order_shipped_email(user_email, user_name, order_number, tracking_url):
    return send_order_tracking_email(user_email, user_name, order_number, 'Shipped', tracking_url)

def queue_order_out_for_delivery_email(user_email, user_name, order_number, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    return send_order_out_for_delivery_email(user_email, user_name, order_number, tracking_url, courier_partner, tracking_number, estimated_delivery_date)

def queue_order_delivered_email(user_email, user_name, order_number):
    return send_order_delivered_email(user_email, user_name, order_number)

def queue_order_status_update_email(order_id, new_status, host_url=None):
    return send_order_status_update_email(order_id, new_status, host_url)
