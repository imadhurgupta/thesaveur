import os
import smtplib
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
from email.utils import formatdate, make_msgid, formataddr
from flask import request, has_request_context
from database import get_db
from services.couriers_service import generate_tracking_url, get_courier_metadata
from services.email_templates import get_email_template


def _strip_html(html_str):
    """Simple helper to create a clean plain-text fallback from HTML."""
    clean = re.sub(r'<[^>]+>', ' ', html_str)
    return re.sub(r'\s+', ' ', clean).strip()


def _build_smtp_headers(msg, subject, receiver_email, smtp_sender):
    """Set standard RFC-compliant email headers to maximize inbox delivery."""
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = formataddr(('The Saveur', smtp_sender))
    msg['To'] = receiver_email
    msg['Reply-To'] = smtp_sender
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='thesaveur.com')
    msg['Auto-Submitted'] = 'auto-generated'
    msg['X-Auto-Response-Suppress'] = 'All'


def _get_smtp_credentials():
    """Retrieve SMTP settings supporting both SMTP_HOST and SMTP_SERVER env keys."""
    smtp_host = os.environ.get('SMTP_HOST') or os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = os.environ.get('SMTP_PORT', '587')
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    smtp_sender = os.environ.get('SMTP_SENDER', smtp_user)
    return smtp_host, smtp_port, smtp_user, smtp_password, smtp_sender


def send_custom_html_email(receiver_email, subject, html_body, plain_body=None):
    """General custom HTML email sending function via SMTP with plain-text fallback."""
    smtp_host, smtp_port, smtp_user, smtp_password, smtp_sender = _get_smtp_credentials()

    if not all([smtp_host, smtp_port, smtp_user, smtp_password]):
        print(f"[SMTP] SMTP variables not fully set. Skip sending '{subject}'.")
        return False

    try:
        port = int(smtp_port)
        msg = MIMEMultipart('alternative')
        _build_smtp_headers(msg, subject, receiver_email, smtp_sender)
        
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

        server.sendmail(smtp_sender, receiver_email, msg.as_string())
        server.quit()
        print(f"[SMTP] Successfully sent custom email '{subject}' to {receiver_email}")
        return True
    except Exception as e:
        print(f"[SMTP] Failed to send custom email to {receiver_email}: {str(e)}")
        return False


def send_otp_email(receiver_email, otp, purpose='reset'):
    """Dispatch OTP email for verification or password reset with high inbox deliverability."""
    print(f"[OTP DISPATCH] Generated {purpose} OTP for {receiver_email}: {otp}")

    smtp_host, smtp_port, smtp_user, smtp_password, smtp_sender = _get_smtp_credentials()

    if not all([smtp_host, smtp_port, smtp_user, smtp_password]):
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
        _build_smtp_headers(msg, subject, receiver_email, smtp_sender)
        msg['X-Priority'] = '1'  # Mark high priority transactional OTP
        
        # 1. Plain text version
        msg.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        
        # 2. HTML version
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
        
        html_body = get_email_template(heading, body_content)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        if port == 465:
            server = smtplib.SMTP_SSL(smtp_host, port, timeout=10)
            server.login(smtp_user, smtp_password)
        else:
            server = smtplib.SMTP(smtp_host, port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_password)

        server.sendmail(smtp_sender, receiver_email, msg.as_string())
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


def send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items):
    """Send order booking confirmation with invoice summary."""
    subject = f"Order Placed Successfully – #{order_number} | The Saveur"
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
    <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been received and is currently being processed. Here are the invoice details:</p>
    
    <h3 style="color: #2D5016; border-bottom: 2px solid #2D5016; padding-bottom: 8px;">Order Details</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <thead>
            <tr style="background-color: #FAF7F2; color: #2D5016; font-weight: bold;">
                <th style="padding: 10px; text-align: left;">Item</th>
                <th style="padding: 10px; text-align: center;">Qty</th>
                <th style="padding: 10px; text-align: right;">Price</th>
                <th style="padding: 10px; text-align: right;">Total</th>
            </tr>
        </thead>
        <tbody>
            {items_rows}
        </tbody>
    </table>
    
    <div style="margin-top: 20px; text-align: right; font-size: 16px; font-weight: bold; color: #2D5016;">
        Total Amount: ${total_amount:.2f}
    </div>
    
    <div style="background-color: #FAF7F2; border-radius: 8px; padding: 15px; margin-top: 20px;">
        <strong style="color: #2D5016; font-size: 14px;">Shipping Address:</strong><br>
        <span style="font-size: 14px; color: #3d3d3d;">{shipping_address}</span>
    </div>
    """
    html_body = get_email_template("Thank You for Your Order!", body_content)
    send_custom_html_email(user_email, subject, html_body)


def send_order_shipped_email(user_email, user_name, order_number, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    """Notify user of order shipment with courier details, AWB, EDD, and live tracking links."""
    subject = f"Your Order #{order_number} is Shipped! 🚚 | The Saveur"
    courier_meta = get_courier_metadata(courier_partner) if courier_partner else None
    courier_display = courier_meta['name'] if courier_meta else (courier_partner or 'Express Courier Partner')

    courier_info_html = ""
    if courier_partner or tracking_number or estimated_delivery_date:
        courier_info_html = f"""
        <div style="background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 14px; padding: 20px; margin: 24px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                <tr>
                    <td style="padding-bottom: 12px; font-size: 13px; color: #64748b; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;" colspan="2">
                        📦 Shipment Details
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; font-size: 14px; color: #475569; font-weight: 600;">Courier Partner:</td>
                    <td style="padding: 6px 0; font-size: 14px; color: #0f172a; font-weight: 700; text-align: right;">{courier_display}</td>
                </tr>
                {f'''<tr>
                    <td style="padding: 6px 0; font-size: 14px; color: #475569; font-weight: 600;">Tracking / AWB No:</td>
                    <td style="padding: 6px 0; font-size: 14px; color: #059669; font-weight: 700; font-family: monospace; text-align: right;">{tracking_number}</td>
                </tr>''' if tracking_number else ''}
                {f'''<tr>
                    <td style="padding: 6px 0; font-size: 14px; color: #475569; font-weight: 600;">Estimated Delivery:</td>
                    <td style="padding: 6px 0; font-size: 14px; color: #d97706; font-weight: 700; text-align: right;">{estimated_delivery_date}</td>
                </tr>''' if estimated_delivery_date else ''}
            </table>
        </div>
        """

    official_courier_url = generate_tracking_url(courier_partner, tracking_number) if (courier_partner and tracking_number) else None

    courier_button_html = ""
    if official_courier_url:
        courier_button_html = f"""
        <div style="margin-top: 14px;">
            <a href="{official_courier_url}" target="_blank" style="color: #059669; font-size: 13px; font-weight: 600; text-decoration: underline;">
                Track Directly on {courier_display} Official Site &rarr;
            </a>
        </div>
        """

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px; margin-bottom: 12px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.6;">Good news! Your order <strong>#{order_number}</strong> has been dispatched and is currently in transit with <strong>{courier_display}</strong>.</p>
    
    {courier_info_html}
    
    <div style="text-align: center; margin: 30px 0;">
        <a href="{tracking_url}" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 99px; font-weight: 700; font-size: 15px; box-shadow: 0 4px 14px rgba(16,185,129,0.3); display: inline-block;">
            📍 Live Tracking Portal
        </a>
        {courier_button_html}
    </div>
    
    <p style="color: #6b6b6b; font-size: 13px; text-align: center;">You can track real-time delivery checkpoints and live status updates using the link above.</p>
    """
    html_body = get_email_template("Your Order has Shipped!", body_content)
    send_custom_html_email(user_email, subject, html_body)


def send_order_delivered_email(user_email, user_name, order_number):
    """Notify user of successful delivery."""
    subject = f"Your Order #{order_number} is Delivered! 🎉 | The Saveur"
    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been successfully delivered. We hope you love your premium teas and spices!</p>
    <p style="color: #3d3d3d; font-size: 15px;">Thank you for shopping with The Saveur.</p>
    """
    html_body = get_email_template("Order Delivered!", body_content)
    send_custom_html_email(user_email, subject, html_body)


def send_order_status_update_email(order_id, new_status, host_url=None):
    """Fetch order details and send status update email based on current state."""
    db = get_db()
    order = db.execute(
        """
        SELECT o.order_number, o.courier_partner, o.tracking_number, o.tracking_url, o.estimated_delivery_date, u.full_name, u.email 
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
        """,
        (order_id,)
    ).fetchone()
    db.close()

    if not order:
        return

    user_email = order['email']
    user_name = order['full_name']
    order_number = order['order_number']

    if new_status == 'Shipped':
        if not host_url and has_request_context():
            host_url = request.host_url
        if not host_url:
            host_url = "https://thesaveur.com/"
        tracking_url = f"{host_url}track-order/{order_id}"

        send_order_shipped_email(
            user_email=user_email,
            user_name=user_name,
            order_number=order_number,
            tracking_url=tracking_url,
            courier_partner=order['courier_partner'],
            tracking_number=order['tracking_number'],
            estimated_delivery_date=order['estimated_delivery_date']
        )
    elif new_status == 'Delivered':
        send_order_delivered_email(user_email, user_name, order_number)
    elif new_status == 'Cancelled':
        subject = f"Your Order #{order_number} has been Cancelled – The Saveur"
        body_content = f"""
        <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
        <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been cancelled. If you paid online, the refund will be initiated to your source account.</p>
        <p style="color: #3d3d3d; font-size: 15px;">If you have any questions, please contact our support team.</p>
        """
        html_body = get_email_template("Order Cancelled", body_content, banner_color_start="#e74c3c", banner_color_end="#c0392b")
        send_custom_html_email(user_email, subject, html_body)


# Queue dispatchers with fallback to synchronous execution
def queue_otp_email(receiver_email, otp, purpose='reset'):
    return send_otp_email(receiver_email, otp, purpose)

def queue_login_alert_email(user_email, user_name):
    return send_login_alert_email(user_email, user_name)

def queue_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items):
    return send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items)

def queue_order_shipped_email(user_email, user_name, order_number, tracking_url):
    return send_order_shipped_email(user_email, user_name, order_number, tracking_url)

def queue_order_delivered_email(user_email, user_name, order_number):
    return send_order_delivered_email(user_email, user_name, order_number)

def queue_order_status_update_email(order_id, new_status, host_url=None):
    return send_order_status_update_email(order_id, new_status, host_url)
