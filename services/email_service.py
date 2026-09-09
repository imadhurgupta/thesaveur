import os
import smtplib
import re
import threading
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
    elif purpose == 'order_deletion':
        subject = f"{otp} is your order deletion verification code – The Saveur"
        heading = "Authorize Permanent Order Deletion"
        body_text = ("A security request was initiated to permanently delete an order record from The Saveur system. "
                     "Enter the 6-digit code below to confirm and authorize permanent deletion. "
                     "This OTP is valid for 10 minutes. If you did not initiate this action, do not share this code.")
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
    Render a 4-stage tracking progress bar for email clients:
    Order Confirmed -> Shipped (Picked Up) -> In Transit (All activities till delivery) -> Delivered
    """
    stages = [
        ('Order Confirmed', 'Confirmed'),
        ('Shipped', 'Shipped'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered')
    ]
    status_ranks = {
        'Order Confirmed': 1,
        'Processing': 1,
        'Placed': 1,
        'Shipped': 2,
        'In Transit': 3,
        'Out for Delivery': 3,  # mapped to In Transit
        'Delivered': 4
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
        <td style="width: 25%; padding: 4px 2px; text-align: center; vertical-align: top;">
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
# ADMIN EMAIL NOTIFICATIONS & HELPERS
# ══════════════════════════════════════════════════════════════════════
def _get_admin_notification_emails():
    """
    Retrieve destination email addresses for store administrators.
    Checks:
    1. system_settings (ADMIN_NOTIFICATION_EMAIL, ADMIN_EMAIL)
    2. users table (is_admin = 1)
    3. os.environ (ADMIN_EMAIL, ADMIN_NOTIFICATION_EMAIL, NOTIFICATION_EMAIL)
    4. Fallbacks: SMTP_USER or admin@thesaveur.com
    """
    admin_emails = []

    # 1. System settings from database
    try:
        db = get_db()
        settings_keys = ['ADMIN_NOTIFICATION_EMAIL', 'ADMIN_EMAIL', 'admin_email', 'admin_notification_email', 'NOTIFICATION_EMAIL']
        for key in settings_keys:
            row = db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
            if row and row['value']:
                for val in re.split(r'[,;\s]+', str(row['value']).strip()):
                    if val and '@' in val:
                        admin_emails.append(val.strip().lower())

        # 2. Registered system administrators
        admin_users = db.execute("SELECT email FROM users WHERE is_admin = 1 AND email IS NOT NULL AND email != ''").fetchall()
        for u in admin_users:
            em = str(u['email']).strip().lower()
            if em and '@' in em:
                admin_emails.append(em)
        db.close()
    except Exception as db_err:
        print(f"[ADMIN EMAIL RESOLVE ERROR] {db_err}")

    # 3. Environment variables
    for env_key in ['ADMIN_EMAIL', 'ADMIN_NOTIFICATION_EMAIL', 'NOTIFICATION_EMAIL']:
        val = os.environ.get(env_key, '').strip()
        if val:
            for em in re.split(r'[,;\s]+', val):
                if em and '@' in em:
                    admin_emails.append(em.strip().lower())

    # 4. Fallback if empty
    if not admin_emails:
        smtp_user = os.environ.get('SMTP_USER', '').strip()
        if smtp_user and '@' in smtp_user:
            admin_emails.append(smtp_user.lower())
        else:
            admin_emails.append('admin@thesaveur.com')

    # Deduplicate while preserving insertion order
    seen = set()
    unique_admins = []
    for email in admin_emails:
        if email not in seen:
            seen.add(email)
            unique_admins.append(email)

    return unique_admins


def send_admin_order_notification(order_data, new_status, old_status=None, items=None, host_url=None):
    """
    Dispatch an executive alert to store administrators for every order status event:
    New booking, Payment confirmation, Shipped, In Transit, Out for delivery, Delivered, Cancelled, Refunded, etc.
    """
    admin_recipients = _get_admin_notification_emails()
    if not admin_recipients:
        print("[ADMIN ALERT] No admin email configured. Skipping admin dispatch.")
        return False

    order_number = order_data.get('order_number') or f"#{order_data.get('id', '')}"
    order_id = order_data.get('id') or order_data.get('order_id')
    customer_name = order_data.get('contact_name') or order_data.get('user_full_name') or order_data.get('full_name') or 'Customer'
    customer_email = order_data.get('contact_email') or order_data.get('user_email') or order_data.get('email') or 'N/A'
    customer_phone = order_data.get('contact_phone') or order_data.get('user_phone') or order_data.get('phone') or 'N/A'
    total_amount = float(order_data.get('total_amount') or 0.0)
    payment_method = order_data.get('payment_method') or 'Online / Prepaid'
    courier_partner = order_data.get('courier_partner', '')
    tracking_number = order_data.get('tracking_number', '')
    tracking_url = order_data.get('tracking_url', '')
    estimated_delivery = order_data.get('estimated_delivery_date', '')
    refund_id = order_data.get('refund_id', '')
    refund_status = order_data.get('refund_status', '')
    refund_amount = float(order_data.get('refund_amount') or 0.0)

    # Shipping Address formulation
    raw_addr = order_data.get('shipping_address', '')
    city = order_data.get('city', '')
    state = order_data.get('state', '')
    zip_code = order_data.get('zip_code', '')
    if city and state and city not in raw_addr:
        full_address = f"{raw_addr}, {city}, {state} – {zip_code}".strip(' ,-–')
    else:
        full_address = raw_addr or 'N/A'

    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    order_ref = str(order_number).lstrip('#') if order_number else str(order_id)
    admin_order_url = f"{host_url.rstrip('/')}/admin/orders/{order_ref}"

    # Visual Theme by Status
    theme_colors = {
        'Placed': ('#2D5016', '#FAF7F2', '#166534'),
        'Order Confirmed': ('#2D5016', '#FAF7F2', '#166534'),
        'Processing': ('#0d9488', '#f0fdfa', '#0f766e'),
        'Shipped': ('#0284c7', '#f0f9ff', '#0369a1'),
        'In Transit': ('#3b82f6', '#eff6ff', '#1d4ed8'),
        'Delivered': ('#16a34a', '#f0fdf4', '#15803d'),
        'Cancelled': ('#dc2626', '#fef2f2', '#b91c1c'),
        'Refunded': ('#7c3aed', '#faf5ff', '#6d28d9'),
    }
    banner_color, badge_bg, badge_text_color = theme_colors.get(new_status, ('#475569', '#f8fafc', '#334155'))

    # Items table construction
    items_rows_html = ""
    items_plain_text = ""
    if items:
        for itm in items:
            p_name = itm.get('product_name') or itm.get('name') or 'Product'
            qty = itm.get('quantity', 1)
            prc = float(itm.get('price', 0.0))
            subt = qty * prc
            items_rows_html += f"""
            <tr>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; color: #1e293b;">{p_name}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: center; color: #1e293b;">{qty}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: right; color: #1e293b;">${prc:.2f}</td>
                <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-size: 13px; text-align: right; font-weight: 600; color: #1e293b;">${subt:.2f}</td>
            </tr>
            """
            items_plain_text += f"- {p_name} x{qty} (${prc:.2f} each = ${subt:.2f})\n"
    else:
        items_rows_html = """<tr><td colspan="4" style="padding: 10px; text-align: center; color: #64748b; font-size: 13px;">Item details available in admin dashboard.</td></tr>"""

    # Optional Tracking info HTML block
    courier_block_html = ""
    if courier_partner or tracking_number or estimated_delivery:
        courier_meta = get_courier_metadata(courier_partner) if courier_partner else None
        courier_disp = courier_meta['name'] if courier_meta else (courier_partner or 'Logistics Partner')
        courier_block_html = f"""
        <div style="background-color: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; margin-bottom: 18px;">
            <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; margin-bottom: 8px;">Shipment &amp; Logistics</div>
            <table width="100%" style="font-size: 13px; border-collapse: collapse;">
                <tr>
                    <td style="padding: 3px 0; color: #64748b; width: 40%;">Courier Partner:</td>
                    <td style="padding: 3px 0; font-weight: 600; color: #0f172a; text-align: right;">{courier_disp}</td>
                </tr>
                {f'''<tr>
                    <td style="padding: 3px 0; color: #64748b;">AWB / Tracking Number:</td>
                    <td style="padding: 3px 0; font-weight: 700; font-family: monospace; color: #059669; text-align: right;">{tracking_number}</td>
                </tr>''' if tracking_number else ''}
                {f'''<tr>
                    <td style="padding: 3px 0; color: #64748b;">Estimated Delivery:</td>
                    <td style="padding: 3px 0; font-weight: 600; color: #d97706; text-align: right;">{estimated_delivery}</td>
                </tr>''' if estimated_delivery else ''}
            </table>
            {f'''<div style="margin-top: 10px; text-align: right;">
                <a href="{tracking_url}" target="_blank" style="color: #0284c7; font-size: 12px; font-weight: 600; text-decoration: underline;">Open Live Tracking &rarr;</a>
            </div>''' if tracking_url else ''}
        </div>
        """

    # Optional Refund info HTML block
    refund_block_html = ""
    if refund_id or refund_status or (new_status in ['Cancelled', 'Refunded'] and refund_amount > 0):
        refund_block_html = f"""
        <div style="background-color: #fef2f2; border: 1.5px solid #fecaca; border-radius: 8px; padding: 14px 16px; margin-bottom: 18px;">
            <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #b91c1c; letter-spacing: 0.5px; margin-bottom: 8px;">Refund Record</div>
            <table width="100%" style="font-size: 13px; border-collapse: collapse;">
                {f'''<tr>
                    <td style="padding: 3px 0; color: #7f1d1d; width: 40%;">Refund ID:</td>
                    <td style="padding: 3px 0; font-family: monospace; font-weight: 600; color: #991b1b; text-align: right;">{refund_id}</td>
                </tr>''' if refund_id else ''}
                {f'''<tr>
                    <td style="padding: 3px 0; color: #7f1d1d;">Refund Amount:</td>
                    <td style="padding: 3px 0; font-weight: 700; color: #991b1b; text-align: right;">${refund_amount:.2f}</td>
                </tr>''' if refund_amount else ''}
                {f'''<tr>
                    <td style="padding: 3px 0; color: #7f1d1d;">Refund Status:</td>
                    <td style="padding: 3px 0; font-weight: 700; text-transform: capitalize; color: #991b1b; text-align: right;">{refund_status or 'Initiated'}</td>
                </tr>''' if refund_status else ''}
            </table>
        </div>
        """

    now_str = datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")
    subject = f"[Admin Alert] Order #{order_number} – {new_status} | The Saveur"

    body_content = f"""
    <!-- Status Highlight Badge -->
    <div style="background-color: {badge_bg}; border: 1.5px solid {banner_color}; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; text-align: center;">
        <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #64748b; font-weight: 600;">Current Order Status</span>
        <div style="font-size: 18px; font-weight: 800; color: {badge_text_color}; margin-top: 4px;">
            {new_status.upper()}
        </div>
        {f'''<div style="font-size: 12px; color: #64748b; margin-top: 2px;">Transitioned from <strong>{old_status}</strong></div>''' if (old_status and old_status != new_status) else ''}
        <div style="font-size: 11px; color: #94a3b8; margin-top: 6px;">Logged at: {now_str}</div>
    </div>

    <!-- Order Financial Overview -->
    <div style="background-color: #fafaf9; border: 1px solid #e7e5e4; border-radius: 8px; padding: 14px 16px; margin-bottom: 18px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #78716c; letter-spacing: 0.5px; margin-bottom: 8px;">Order &amp; Payment Overview</div>
        <table width="100%" style="font-size: 13px; border-collapse: collapse;">
            <tr>
                <td style="padding: 3px 0; color: #57534e;">Order Number:</td>
                <td style="padding: 3px 0; font-weight: 700; color: #1c1917; text-align: right;">#{order_number}</td>
            </tr>
            <tr>
                <td style="padding: 3px 0; color: #57534e;">Total Amount:</td>
                <td style="padding: 3px 0; font-weight: 800; color: #2D5016; text-align: right; font-size: 15px;">${total_amount:.2f}</td>
            </tr>
            <tr>
                <td style="padding: 3px 0; color: #57534e;">Payment Method:</td>
                <td style="padding: 3px 0; font-weight: 600; color: #1c1917; text-align: right;">{payment_method}</td>
            </tr>
        </table>
    </div>

    <!-- Customer Profile -->
    <div style="background-color: #FAF7F2; border: 1px solid #EAE6DF; border-radius: 8px; padding: 14px 16px; margin-bottom: 18px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #78716c; letter-spacing: 0.5px; margin-bottom: 8px;">Customer Information</div>
        <table width="100%" style="font-size: 13px; border-collapse: collapse;">
            <tr>
                <td style="padding: 3px 0; color: #57534e; width: 35%;">Customer Name:</td>
                <td style="padding: 3px 0; font-weight: 600; color: #1c1917; text-align: right;">{customer_name}</td>
            </tr>
            <tr>
                <td style="padding: 3px 0; color: #57534e;">Email:</td>
                <td style="padding: 3px 0; text-align: right;"><a href="mailto:{customer_email}" style="color: #2D5016; text-decoration: underline; font-weight: 600;">{customer_email}</a></td>
            </tr>
            <tr>
                <td style="padding: 3px 0; color: #57534e;">Phone:</td>
                <td style="padding: 3px 0; text-align: right;"><a href="tel:{customer_phone}" style="color: #2D5016; text-decoration: none; font-weight: 600;">{customer_phone}</a></td>
            </tr>
            <tr>
                <td style="padding: 6px 0 2px; color: #57534e; vertical-align: top;">Shipping Address:</td>
                <td style="padding: 6px 0 2px; color: #1c1917; text-align: right; line-height: 1.3; font-weight: 500;">{full_address}</td>
            </tr>
        </table>
    </div>

    {courier_block_html}
    {refund_block_html}

    <!-- Items Breakdown -->
    <div style="margin-bottom: 22px;">
        <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #2D5016; letter-spacing: 0.5px; margin-bottom: 8px; border-bottom: 1.5px solid #2D5016; padding-bottom: 4px;">Items in Order</div>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
            <thead>
                <tr style="background-color: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700;">
                    <th style="padding: 8px 10px; text-align: left;">Product</th>
                    <th style="padding: 8px 10px; text-align: center;">Qty</th>
                    <th style="padding: 8px 10px; text-align: right;">Unit Price</th>
                    <th style="padding: 8px 10px; text-align: right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {items_rows_html}
            </tbody>
        </table>
    </div>

    <!-- Admin Dashboard CTA -->
    <div style="text-align: center; margin: 26px 0 14px;">
        <a href="{admin_order_url}" style="background-color: #2D5016; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block; box-shadow: 0 3px 8px rgba(45,80,22,0.25);">
            Manage Order in Admin Portal &rarr;
        </a>
    </div>
    """

    plain_body = f"""[Admin Alert] Order #{order_number} Status: {new_status}
Logged at: {now_str}

Customer: {customer_name} ({customer_email} | {customer_phone})
Shipping Address: {full_address}

Total Amount: ${total_amount:.2f}
Payment Method: {payment_method}
Courier: {courier_partner or 'Not Assigned'} (AWB: {tracking_number or 'N/A'})

Items:
{items_plain_text}

Manage this order in Admin Panel: {admin_order_url}
"""

    html_template = get_email_template(
        f"Admin Alert: Order #{order_number} – {new_status}",
        body_content,
        banner_color_start=banner_color,
        footer_note="Automated operational alert for The Saveur administrators."
    )

    success_count = 0
    for admin_email in admin_recipients:
        res = send_custom_html_email(admin_email, subject, html_template, plain_body=plain_body)
        if res:
            success_count += 1

    print(f"[ADMIN ALERT] Dispatched status '{new_status}' for order #{order_number} to {success_count}/{len(admin_recipients)} admin recipient(s).")
    return success_count > 0


# ══════════════════════════════════════════════════════════════════════
# 1. ORDER CONFIRMED & BOOKING EMAIL
# ══════════════════════════════════════════════════════════════════════
def send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items, host_url=None, notify_admin=True, payment_method=None, user_phone=None):
    """Send order booking confirmation with 5-stage progress indicator, invoice summary, and optional admin alert."""
    subject = f"Order Confirmed – #{order_number} | The Saveur"
    stepper_html = _render_email_tracking_stepper('Order Confirmed')

    items_rows = ""
    for item in items:
        p_name = item.get('product_name') or item.get('name') or 'Product'
        qty = item.get('quantity', 1)
        price = float(item.get('price', 0.0))
        subtotal = qty * price
        items_rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee;">{p_name}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: center;">{qty}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">${price:.2f}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">${subtotal:.2f}</td>
        </tr>
        """
    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">Thank you for shopping with The Saveur! Your order <strong>#{order_number}</strong> has been confirmed and is being carefully packed for shipment.</p>
    
    {stepper_html}

    <div style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; padding: 12px 16px; margin: 16px 0; text-align: center;">
        <span style="font-size: 13px; font-weight: 700; color: #166534;">Status: Order Confirmed</span>
        <div style="font-size: 12px; color: #15803d; margin-top: 2px;">We will send you a tracking email with courier details as soon as your order is dispatched.</div>
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
        Total Amount: ${float(total_amount):.2f}
    </div>
    
    <div style="background-color: #FAF7F2; border-radius: 8px; padding: 12px 14px; margin-top: 18px;">
        <strong style="color: #2D5016; font-size: 12px; text-transform: uppercase;">Shipping Address:</strong><br>
        <span style="font-size: 13px; color: #3d3d3d; line-height: 1.4;">{shipping_address}</span>
    </div>
    """
    html_body = get_email_template("Your Order is Confirmed", body_content, footer_note="Thank you for ordering from The Saveur.")
    cust_res = send_custom_html_email(user_email, subject, html_body)

    # Automatically notify administrator of the newly booked order
    if notify_admin:
        try:
            admin_payload = {
                'order_number': order_number,
                'contact_name': user_name,
                'contact_email': user_email,
                'contact_phone': user_phone or 'N/A',
                'total_amount': total_amount,
                'shipping_address': shipping_address,
                'payment_method': payment_method or 'Confirmed'
            }
            send_admin_order_notification(admin_payload, new_status='Order Confirmed', items=items, host_url=host_url)
        except Exception as admin_err:
            print(f"[ADMIN ORDER ALERT ERROR] {admin_err}")

    return cust_res


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
        'In Transit': 'Your Package is In Transit'
    }
    status_descriptions = {
        'Shipped': f"Great news! Your order <strong>#{order_number}</strong> has been picked up by <strong>{courier_display}</strong> and is dispatched.",
        'In Transit': f"Your package for order <strong>#{order_number}</strong> is in transit between logistics checkpoints with <strong>{courier_display}</strong>."
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
    return send_custom_html_email(user_email, subject, html_body)


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
    """Explicit helper for Out for Delivery status email (mapped to In Transit)."""
    return send_order_tracking_email(
        user_email=user_email,
        user_name=user_name,
        order_number=order_number,
        status='In Transit',
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
    return send_custom_html_email(user_email, subject, html_body)


# ══════════════════════════════════════════════════════════════════════
# 5. CANCELLED & REFUNDED EMAILS
# ══════════════════════════════════════════════════════════════════════
def send_order_cancelled_email(user_email, user_name, order_number, total_amount=0, refund_id=None, refund_amount=0, is_cod=False, host_url=None):
    """Send a respectful and clear order cancellation notification to customer."""
    subject = f"Your Order #{order_number} has been Cancelled – The Saveur"
    
    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    shop_url = f"{host_url.rstrip('/')}/products"

    if is_cod:
        refund_note = "<p style='color: #3d3d3d; font-size: 14px;'>Since your order was placed with <strong>Cash on Delivery</strong>, no payment was charged or deducted.</p>"
    elif refund_id:
        refund_note = f"""
        <div style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; padding: 14px; margin: 18px 0;">
            <div style="font-size: 13px; font-weight: 700; color: #166534;">Refund Reference: #{refund_id}</div>
            <div style="font-size: 12px; color: #15803d; margin-top: 4px;">
                A refund of <strong>${float(refund_amount or total_amount):.2f}</strong> has been initiated back to your original payment method. Depending on your bank, it typically reflects within 5–7 business days.
            </div>
        </div>
        """
    else:
        refund_note = "<p style='color: #3d3d3d; font-size: 14px;'>If payment was already completed online, our automated refund will be credited back to your original payment account within 5–7 business days.</p>"

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">
        Your order <strong>#{order_number}</strong> has been cancelled.
    </p>

    {refund_note}

    <div style="background-color: #fef2f2; border: 1.5px solid #fecaca; border-radius: 8px; padding: 14px 18px; margin: 20px 0; text-align: center;">
        <span style="font-size: 13px; font-weight: 700; color: #991b1b;">Order Status: Cancelled</span>
        <div style="font-size: 12px; color: #b91c1c; margin-top: 2px;">
            Order reference: #{order_number} &bull; Total Value: ${float(total_amount):.2f}
        </div>
    </div>

    <p style="color: #6b6b6b; font-size: 13px; line-height: 1.5;">
        If you did not request this cancellation or have any questions regarding your refund, please feel free to reach out to our dedicated support team at <a href="mailto:info@thesaveur.com" style="color: #2D5016; font-weight: 600;">info@thesaveur.com</a>.
    </p>

    <div style="text-align: center; margin: 24px 0 12px;">
        <a href="{shop_url}" style="background-color: #2D5016; color: #ffffff; padding: 12px 26px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">
            Continue Shopping at The Saveur
        </a>
    </div>
    """

    html_body = get_email_template("Order Cancelled", body_content, banner_color_start="#dc2626", banner_color_end="#991b1b", footer_note="Order cancellation and refund notification from The Saveur.")
    return send_custom_html_email(user_email, subject, html_body)


def send_order_refunded_email(user_email, user_name, order_number, refund_id=None, refund_amount=0, host_url=None):
    """Notify customer that refund has been processed for their order."""
    subject = f"Refund Confirmation for Order #{order_number} | The Saveur"
    
    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">
        We have successfully processed the refund for your order <strong>#{order_number}</strong>.
    </p>

    <div style="background-color: #faf5ff; border: 1.5px solid #e9d5ff; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <table width="100%" style="font-size: 13px; border-collapse: collapse;">
            <tr>
                <td style="padding: 4px 0; color: #6b21a8; font-weight: 600;">Refund Reference:</td>
                <td style="padding: 4px 0; font-family: monospace; font-weight: 700; color: #581c87; text-align: right;">{refund_id or 'Auto-Processed'}</td>
            </tr>
            <tr>
                <td style="padding: 4px 0; color: #6b21a8; font-weight: 600;">Refunded Amount:</td>
                <td style="padding: 4px 0; font-weight: 800; color: #581c87; font-size: 15px; text-align: right;">${float(refund_amount):.2f}</td>
            </tr>
            <tr>
                <td style="padding: 4px 0; color: #6b21a8; font-weight: 600;">Settlement Timeline:</td>
                <td style="padding: 4px 0; color: #581c87; text-align: right;">5–7 Business Days</td>
            </tr>
        </table>
    </div>

    <p style="color: #6b6b6b; font-size: 13px; line-height: 1.5;">
        Depending on your card issuer or bank, the amount will be credited directly to your original source account. If you require further assistance, please contact <a href="mailto:info@thesaveur.com" style="color: #2D5016; font-weight: 600;">info@thesaveur.com</a>.
    </p>
    """

    html_body = get_email_template("Refund Processed", body_content, banner_color_start="#7c3aed", banner_color_end="#581c87", footer_note="Official refund receipt from The Saveur.")
    return send_custom_html_email(user_email, subject, html_body)


def send_generic_order_status_email(user_email, user_name, order_number, status, host_url=None):
    """Fallback dispatcher for any arbitrary order status update."""
    subject = f"Order #{order_number} Status Update: {status} | The Saveur"
    
    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    track_url = f"{host_url.rstrip('/')}/my-orders"

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px; line-height: 1.5;">
        The status of your order <strong>#{order_number}</strong> has been updated to:
    </p>

    <div style="background-color: #FAF7F2; border: 1.5px solid #2D5016; border-radius: 8px; padding: 14px 18px; margin: 20px 0; text-align: center;">
        <span style="font-size: 11px; text-transform: uppercase; color: #78716c; font-weight: 600;">Updated Status</span>
        <div style="font-size: 16px; font-weight: 800; color: #2D5016; margin-top: 4px;">{status}</div>
    </div>

    <div style="text-align: center; margin: 24px 0 12px;">
        <a href="{track_url}" style="background-color: #2D5016; color: #ffffff; padding: 12px 26px; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">
            View Order in My Account
        </a>
    </div>
    """

    html_body = get_email_template(f"Order Status: {status}", body_content, footer_note="Order update notice from The Saveur.")
    return send_custom_html_email(user_email, subject, html_body)


# ══════════════════════════════════════════════════════════════════════
# MAIN STATUS DISPATCHER
# ══════════════════════════════════════════════════════════════════════
def send_order_status_update_email(order_id, new_status, host_url=None):
    """
    Fetch order details and dispatch appropriate emails for EVERY order lifecycle status:
    - Order Confirmed / Processing / Placed
    - Shipped / In Transit / Out for Delivery
    - Delivered
    - Cancelled
    - Refunded
    - Any other status

    Simultaneously dispatches administrative notification to store administrators.
    """
    db = get_db()
    order = db.execute(
        """
        SELECT o.*,
               u.full_name as user_full_name, u.email as user_email, u.phone as user_phone 
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
        """,
        (order_id,)
    ).fetchone()

    if not order:
        db.close()
        print(f"[ORDER STATUS EMAIL] Order #{order_id} not found.")
        return

    order_dict = dict(order)

    # Fetch order items
    items = db.execute(
        """
        SELECT oi.*, p.name as product_name
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
        """,
        (order_id,)
    ).fetchall()
    db.close()
    items_list = [dict(i) for i in items]

    # Resolve Customer contact credentials
    user_email = order_dict.get('contact_email') or order_dict.get('user_email')
    user_name = order_dict.get('contact_name') or order_dict.get('user_full_name') or 'Valued Customer'
    user_phone = order_dict.get('contact_phone') or order_dict.get('user_phone') or 'N/A'
    order_number = order_dict.get('order_number') or f"#{order_id}"
    total_amount = float(order_dict.get('total_amount') or 0.0)

    addr_parts = [p for p in [order_dict.get('shipping_address'), order_dict.get('city'), order_dict.get('state')] if p]
    zip_p = order_dict.get('zip_code')
    shipping_addr_full = f"{', '.join(addr_parts)} – {zip_p}" if zip_p else ', '.join(addr_parts)

    if not host_url and has_request_context():
        host_url = request.host_url
    if not host_url:
        host_url = "https://thesaveur.com/"
    
    token = generate_order_access_token(order_dict.get('id'), order_dict.get('user_id'), order_dict.get('order_number') or '')
    tracking_ref = order_dict.get('order_number') or order_id
    tracking_url = f"{host_url.rstrip('/')}/track-order/{tracking_ref}?token={token}"

    # 1. DISPATCH TO RELATED CUSTOMER
    if user_email:
        try:
            if new_status in ['Order Confirmed', 'Processing', 'Placed']:
                send_order_confirmation_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    total_amount=total_amount,
                    shipping_address=shipping_addr_full,
                    items=items_list,
                    host_url=host_url,
                    notify_admin=False  # Admin notified explicitly below
                )
            elif new_status in ['Shipped', 'In Transit', 'Out for Delivery']:
                normalized_tracking_status = 'In Transit' if new_status == 'Out for Delivery' else new_status
                send_order_tracking_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    status=normalized_tracking_status,
                    tracking_url=tracking_url,
                    courier_partner=order_dict.get('courier_partner'),
                    tracking_number=order_dict.get('tracking_number'),
                    estimated_delivery_date=order_dict.get('estimated_delivery_date')
                )
            elif new_status == 'Delivered':
                send_order_delivered_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    order_id=order_id,
                    user_id=order_dict.get('user_id'),
                    host_url=host_url
                )
            elif new_status == 'Cancelled':
                is_cod = (str(order_dict.get('payment_method', '')).lower() == 'cod' or 'cash' in str(order_dict.get('payment_method', '')).lower())
                send_order_cancelled_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    total_amount=total_amount,
                    refund_id=order_dict.get('refund_id'),
                    refund_amount=order_dict.get('refund_amount') or total_amount,
                    is_cod=is_cod,
                    host_url=host_url
                )
            elif new_status == 'Refunded':
                send_order_refunded_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    refund_id=order_dict.get('refund_id'),
                    refund_amount=order_dict.get('refund_amount') or total_amount,
                    host_url=host_url
                )
            else:
                send_generic_order_status_email(
                    user_email=user_email,
                    user_name=user_name,
                    order_number=order_number,
                    status=new_status,
                    host_url=host_url
                )
            print(f"[STATUS EMAIL] Customer notification for #{order_number} ({new_status}) dispatched to {user_email}.")
        except Exception as cust_mail_err:
            print(f"[CUSTOMER STATUS MAIL ERROR] {cust_mail_err}")
    else:
        print(f"[STATUS EMAIL WARNING] No customer email found for Order #{order_id}.")

    # 2. DISPATCH TO STORE ADMINISTRATORS
    try:
        order_dict['contact_name'] = user_name
        order_dict['contact_email'] = user_email
        order_dict['contact_phone'] = user_phone
        order_dict['shipping_address'] = shipping_addr_full
        send_admin_order_notification(
            order_data=order_dict,
            new_status=new_status,
            items=items_list,
            host_url=host_url
        )
    except Exception as admin_mail_err:
        print(f"[ADMIN STATUS MAIL ERROR] {admin_mail_err}")


# ══════════════════════════════════════════════════════════════════════
# QUEUE DISPATCHERS (NON-BLOCKING BACKGROUND THREAD EXECUTION)
# ══════════════════════════════════════════════════════════════════════
def _run_in_background(target_func, *args, **kwargs):
    """Execute email tasks asynchronously in background threads to eliminate UI latency."""
    try:
        thread = threading.Thread(target=target_func, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return thread
    except Exception as th_err:
        print(f"[BACKGROUND THREAD ERROR] Fallback to synchronous dispatch: {th_err}")
        return target_func(*args, **kwargs)


def queue_otp_email(receiver_email, otp, purpose='reset'):
    return _run_in_background(send_otp_email, receiver_email, otp, purpose)


def queue_login_alert_email(user_email, user_name):
    return _run_in_background(send_login_alert_email, user_email, user_name)


def queue_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items, host_url=None):
    if not host_url and has_request_context():
        try:
            host_url = request.host_url
        except Exception:
            pass
    return _run_in_background(send_order_confirmation_email, user_email, user_name, order_number, total_amount, shipping_address, items, host_url=host_url)


def queue_order_shipped_email(user_email, user_name, order_number, tracking_url):
    return _run_in_background(send_order_tracking_email, user_email, user_name, order_number, 'Shipped', tracking_url)


def queue_order_out_for_delivery_email(user_email, user_name, order_number, tracking_url, courier_partner=None, tracking_number=None, estimated_delivery_date=None):
    return _run_in_background(send_order_out_for_delivery_email, user_email, user_name, order_number, tracking_url, courier_partner, tracking_number, estimated_delivery_date)


def queue_order_delivered_email(user_email, user_name, order_number):
    return _run_in_background(send_order_delivered_email, user_email, user_name, order_number)


def queue_order_status_update_email(order_id, new_status, host_url=None):
    if not host_url and has_request_context():
        try:
            host_url = request.host_url
        except Exception:
            pass
    return _run_in_background(send_order_status_update_email, order_id, new_status, host_url=host_url)

