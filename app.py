from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, has_request_context

from database import get_db, init_db, generate_user_id

import hashlib

import random

import razorpay

import string

from datetime import datetime, timedelta

from functools import wraps

import os

from dotenv import load_dotenv

import redis

import json

from celery import Celery



# Load environment variables from .env file

load_dotenv()

from werkzeug.utils import secure_filename

import urllib.parse

import secrets

import requests

import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header



app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'am_trader_dev_secret_key_2024')
app.config['SESSION_COOKIE_NAME'] = 'thesaveur_session'



# Razorpay Configuration

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '').strip()

RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '').strip()

IS_REAL_MODE = True



def get_razorpay_client():

    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:

        try:

            return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

        except Exception as e:

            print(f"[RAZORPAY] Initialization error: {str(e)}")

    return None



# PayPal Configuration

PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', '').strip()

PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET', '').strip()

PAYPAL_MODE = os.environ.get('PAYPAL_MODE', 'sandbox').strip().lower()

PAYPAL_EXCHANGE_RATE = float(os.environ.get('PAYPAL_EXCHANGE_RATE_INR_TO_USD', 0.012) or 0.012)



def get_paypal_api_base():

    if PAYPAL_MODE == 'live':

        return "https://api-m.paypal.com"

    return "https://api-m.sandbox.paypal.com"



def get_paypal_access_token():

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:

        return None

    try:

        url = f"{get_paypal_api_base()}/v1/oauth2/token"

        headers = {

            "Accept": "application/json",

            "Accept-Language": "en_US",

        }

        data = {

            "grant_type": "client_credentials"

        }

        res = requests.post(url, headers=headers, data=data, auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET), timeout=10)

        if res.status_code == 200:

            return res.json().get('access_token')

        else:

            print(f"[PAYPAL] Failed to get access token: {res.status_code} - {res.text}")

    except Exception as e:

        print(f"[PAYPAL] OAuth error: {str(e)}")

    return None



@app.context_processor

def inject_paypal_config():

    return dict(

        paypal_client_id=PAYPAL_CLIENT_ID,

        paypal_mode=PAYPAL_MODE

    )






# Redis Configuration & Initialization

redis_client = None

try:

    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    if redis_url:

        redis_client = redis.Redis.from_url(redis_url, socket_timeout=3)

        redis_client.ping()

        print(f"[REDIS] Connected successfully to {redis_url}")

except Exception as e:

    print(f"[REDIS WARNING] Failed to connect: {e}. Caching is disabled.")

    redis_client = None





def invalidate_cache(*keys):

    if redis_client:

        try:

            for key in keys:

                redis_client.delete(key)

                print(f"[REDIS] Cache invalidated for key: {key}")

        except Exception as e:

            print(f"[REDIS] Cache invalidation error: {e}")





# Celery Configuration & Initialization

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', '').strip()

USE_CELERY = bool(CELERY_BROKER_URL)



celery_app = None

if USE_CELERY:

    try:

        celery_app = Celery(app.name, broker=CELERY_BROKER_URL)

        celery_app.conf.update(

            result_backend=os.environ.get('CELERY_RESULT_BACKEND', 'rpc://'),

            task_ignore_result=True

        )

        print(f"[CELERY] Initialized task queue with broker: {CELERY_BROKER_URL}")

    except Exception as e:

        print(f"[CELERY WARNING] Failed to initialize: {e}. Falling back to sync.")

        USE_CELERY = False







UPLOAD_FOLDER = os.environ.get(

    'UPLOAD_FOLDER',

    os.path.join(os.path.dirname(__file__), 'static', 'images')

)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}



def allowed_file(filename):

    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



# Initialize DB on startup

with app.app_context():

    init_db()



@app.context_processor
def inject_categories():
    if redis_client:
        try:
            cached_val = redis_client.get("nav_categories")
            if cached_val:
                return dict(nav_categories=json.loads(cached_val.decode('utf-8')))
        except Exception as e:
            print(f"[REDIS] Read error in nav context: {e}")

    db = get_db()
    try:
        categories_raw = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        categories = []
        for cat in categories_raw:
            cat_dict = dict(cat)
            subcats = db.execute("SELECT * FROM subcategories WHERE category_name = ? ORDER BY display_order ASC", (cat['name'],)).fetchall()
            cat_dict['subcategories'] = [dict(sub) for sub in subcats]
            categories.append(cat_dict)

        if redis_client:
            try:
                redis_client.setex("nav_categories", 3600, json.dumps(categories))
            except Exception as e:
                print(f"[REDIS] Write error in nav context: {e}")

        return dict(nav_categories=categories)
    except Exception as e:
        print(f"[NAV CONTEXT] Error fetching categories: {e}")
        return dict(nav_categories=[])
    finally:
        db.close()






def generate_order_number():

    """Generate a unique alphanumeric order number, e.g. AMT-A3X9KZ2Q."""

    chars = string.ascii_uppercase + string.digits

    suffix = ''.join(random.choices(chars, k=8))

    return f'AMT-{suffix}'





def hash_password(password):

    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def get_email_template(heading, body_content, banner_color_start="#2D5016", banner_color_end="#5a9e35"):
    return f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, {banner_color_start} 0%, {banner_color_end} 100%); padding: 30px; text-align: center; color: #ffffff;">
                <img src="cid:logo" alt="The Saveur" style="height: 60px; width: 60px; border-radius: 50%; object-fit: cover; border: 2px solid #ffffff; margin-bottom: 10px;" />
                <h1 style="margin: 5px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold; letter-spacing: 1px;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: {banner_color_start}; margin-top: 0; font-size: 20px;">{heading}</h2>
                {body_content}
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_otp_email(receiver_email, otp, purpose='reset'):

    smtp_host = os.environ.get('SMTP_HOST')

    smtp_port = os.environ.get('SMTP_PORT')

    smtp_user = os.environ.get('SMTP_USER')

    smtp_password = os.environ.get('SMTP_PASSWORD')

    smtp_sender = os.environ.get('SMTP_SENDER', smtp_user)

    

    if not all([smtp_host, smtp_port, smtp_user, smtp_password]):

        print("[SMTP] Not fully configured. (Required: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)")

        return False



    if purpose == 'signup':

        subject = "Verify Your Email – The Saveur"

        heading = "Verify Your Email Address"

        body_text = ("You're almost there! Enter the 6-digit code below to verify your email address "

                     "and complete your account registration. This OTP is valid for 10 minutes.")

    elif purpose == 'admin_login':

        subject = "Admin Login OTP – The Saveur"

        heading = "Admin Login Verification"

        body_text = ("An administrator login attempt was detected for your account. Enter the 6-digit code "

                     "below to verify your identity and complete the login. This OTP is valid for 10 minutes.")

    else:

        subject = "Password Reset OTP – The Saveur"

        heading = "Password Reset Request"

        body_text = ("We received a request to reset your password. Use the verification code below "

                     "to proceed with the password reset process. This OTP is valid for 10 minutes.")

        

    try:
        port = int(smtp_port)
        msg = MIMEMultipart('related')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = smtp_sender
        msg['To'] = receiver_email
        
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        # HTML body with premium styling matching brand colors
        body_content = f"""
        <p style="color: #3d3d3d; font-size: 15px;">Hello,</p>
        <p style="color: #3d3d3d; font-size: 15px;">{body_text}</p>
        
        <div style="background-color: #FAF7F2; border: 1px dashed #C8860A; border-radius: 8px; padding: 20px; text-align: center; margin: 30px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #C8860A; font-family: monospace;">{otp}</span>
        </div>
        
        <p style="color: #3d3d3d; font-size: 15px;">If you did not request this, please ignore this email or contact support if you have concerns.</p>
        """
        
        html_body = get_email_template(heading, body_content)
        
        part = MIMEText(html_body, 'html', 'utf-8')
        msg_alternative.attach(part)
        
        # Attach inlined logo
        try:
            with open('static/images/logo.jpg', 'rb') as f:
                img_data = f.read()
            msg_img = MIMEImage(img_data, name='logo.jpg')
            msg_img.add_header('Content-ID', '<logo>')
            msg_img.add_header('Content-Disposition', 'inline', filename='logo.jpg')
            msg.attach(msg_img)
        except Exception as e:
            print(f"[SMTP] Failed to attach inline logo to OTP email: {e}")

        

        # Determine SSL/TLS

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

        print(f"[SMTP] Failed to send email to {receiver_email}: {str(e)}")

        return False





def send_custom_html_email(receiver_email, subject, html_body):

    """General custom HTML email sending function via SMTP."""

    smtp_host = os.environ.get('SMTP_HOST')

    smtp_port = os.environ.get('SMTP_PORT')

    smtp_user = os.environ.get('SMTP_USER')

    smtp_password = os.environ.get('SMTP_PASSWORD')

    smtp_sender = os.environ.get('SMTP_SENDER', smtp_user)

    

    if not all([smtp_host, smtp_port, smtp_user, smtp_password]):

        print(f"[SMTP] SMTP variables not fully set. Skip sending '{subject}'.")

        return False

        

    try:
        port = int(smtp_port)
        msg = MIMEMultipart('related')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = smtp_sender
        msg['To'] = receiver_email
        
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        part = MIMEText(html_body, 'html', 'utf-8')
        msg_alternative.attach(part)
        
        # Attach inlined logo
        try:
            with open('static/images/logo.jpg', 'rb') as f:
                img_data = f.read()
            msg_img = MIMEImage(img_data, name='logo.jpg')
            msg_img.add_header('Content-ID', '<logo>')
            msg_img.add_header('Content-Disposition', 'inline', filename='logo.jpg')
            msg.attach(msg_img)
        except Exception as e:
            print(f"[SMTP] Failed to attach inline logo to custom email: {e}")

        

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

            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">₹{item['price']:.2f}</td>

            <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">₹{subtotal:.2f}</td>

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
        Total Amount: ₹{total_amount:.2f}
    </div>
    
    <div style="background-color: #FAF7F2; border-radius: 8px; padding: 15px; margin-top: 20px;">
        <strong style="color: #2D5016; font-size: 14px;">Shipping Address:</strong><br>
        <span style="font-size: 14px; color: #3d3d3d;">{shipping_address}</span>
    </div>
    """
    html_body = get_email_template("Thank You for Your Order!", body_content)

    send_custom_html_email(user_email, subject, html_body)





def send_order_shipped_email(user_email, user_name, order_number, tracking_url):

    """Notify user of order shipment with tracking link."""

    subject = f"Your Order #{order_number} is Shipped! 🚚 | The Saveur"

    body_content = f"""
    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
    <p style="color: #3d3d3d; font-size: 15px;">Good news! Your order #{order_number} is on the way. Our delivery partner is delivering it to you.</p>
    
    <div style="text-align: center; margin: 30px 0;">
        <a href="{tracking_url}" style="background-color: #C8860A; color: white; padding: 14px 28px; text-decoration: none; border-radius: 99px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 12px rgba(200,134,10,0.3); display: inline-block;">
            📍 Live Tracking Link
        </a>
    </div>
    
    <p style="color: #6b6b6b; font-size: 13px; text-align: center;">Click the button above to track your delivery partner and see live updates.</p>
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

        SELECT o.order_number, u.full_name, u.email 

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

        send_order_shipped_email(user_email, user_name, order_number, tracking_url)

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





# ── Celery Background Tasks ───────────────────────────────────────────────

if USE_CELERY:

    @celery_app.task(name='app.send_otp_email_task')
    def send_otp_email_task(receiver_email, otp, purpose='reset'):
        return send_otp_email(receiver_email, otp, purpose)

    @celery_app.task(name='app.send_login_alert_email_task')
    def send_login_alert_email_task(user_email, user_name):
        return send_login_alert_email(user_email, user_name)

    @celery_app.task(name='app.send_order_confirmation_email_task')
    def send_order_confirmation_email_task(user_email, user_name, order_number, total_amount, shipping_address, items):
        return send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items)

    @celery_app.task(name='app.send_order_shipped_email_task')
    def send_order_shipped_email_task(user_email, user_name, order_number, tracking_url):
        return send_order_shipped_email(user_email, user_name, order_number, tracking_url)

    @celery_app.task(name='app.send_order_delivered_email_task')
    def send_order_delivered_email_task(user_email, user_name, order_number):
        return send_order_delivered_email(user_email, user_name, order_number)

    @celery_app.task(name='app.send_order_status_update_email_task')
    def send_order_status_update_email_task(order_id, new_status, host_url=None):
        return send_order_status_update_email(order_id, new_status, host_url)


# ── Asynchronous Dispatch Helpers ─────────────────────────────────────────

def queue_otp_email(receiver_email, otp, purpose='reset'):
    if USE_CELERY:
        try:
            send_otp_email_task.delay(receiver_email, otp, purpose)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue OTP email: {e}. Executing sync.")
    return send_otp_email(receiver_email, otp, purpose)

def queue_login_alert_email(user_email, user_name):
    if USE_CELERY:
        try:
            send_login_alert_email_task.delay(user_email, user_name)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue login alert: {e}. Executing sync.")
    return send_login_alert_email(user_email, user_name)

def queue_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items):
    if USE_CELERY:
        try:
            send_order_confirmation_email_task.delay(user_email, user_name, order_number, total_amount, shipping_address, items)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue order confirmation email: {e}. Executing sync.")
    return send_order_confirmation_email(user_email, user_name, order_number, total_amount, shipping_address, items)

def queue_order_shipped_email(user_email, user_name, order_number, tracking_url):
    if USE_CELERY:
        try:
            send_order_shipped_email_task.delay(user_email, user_name, order_number, tracking_url)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue order shipped email: {e}. Executing sync.")
    return send_order_shipped_email(user_email, user_name, order_number, tracking_url)

def queue_order_delivered_email(user_email, user_name, order_number):
    if USE_CELERY:
        try:
            send_order_delivered_email_task.delay(user_email, user_name, order_number)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue order delivered email: {e}. Executing sync.")
    return send_order_delivered_email(user_email, user_name, order_number)

def queue_order_status_update_email(order_id, new_status, host_url=None):
    if USE_CELERY:
        try:
            send_order_status_update_email_task.delay(order_id, new_status, host_url)
            return True
        except Exception as e:
            print(f"[CELERY WARNING] Failed to queue status update email: {e}. Executing sync.")
    return send_order_status_update_email(order_id, new_status, host_url)






def admin_required(f):

    @wraps(f)

    def decorated_function(*args, **kwargs):

        if 'user_id' not in session or not session.get('is_admin'):

            flash('Access denied. Administrator privileges required.', 'error')

            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function









# ─────── Template context globals ───────────────────────────────────────────



@app.context_processor

def inject_globals():

    return {

        'site_name': os.environ.get('SITE_NAME', 'The Saveur'),

    }





# ─────── Home ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/')

def home():

    db = get_db()

    bestsellers_raw = db.execute(

        "SELECT * FROM products WHERE is_bestseller = 1 LIMIT 10"

    ).fetchall()

    

    bestsellers = []

    for p in bestsellers_raw:

        p_dict = dict(p)

        stats = db.execute("""

            SELECT COUNT(*) AS count, AVG(rating) AS avg

            FROM reviews

            WHERE product_id = ?

        """, (p['id'],)).fetchone()

        p_dict['review_count'] = stats['count'] if stats else 0

        p_dict['avg_rating'] = round(stats['avg'], 1) if stats and stats['avg'] else 0.0

        bestsellers.append(p_dict)



    carousel_slides = db.execute(

        "SELECT * FROM carousel_slides ORDER BY slide_order ASC"

    ).fetchall()

    categories = db.execute(

        "SELECT * FROM categories ORDER BY display_order ASC"

    ).fetchall()



    # Fetch per-product review stats for the homepage snapshot

    product_reviews = db.execute("""

        SELECT p.id, p.name, p.category, p.image_filename,

               COUNT(r.id) AS review_count,

               ROUND(CAST(AVG(r.rating) AS NUMERIC), 1) AS avg_rating

        FROM products p

        INNER JOIN reviews r ON r.product_id = p.id

        GROUP BY p.id, p.name, p.category, p.image_filename

        HAVING COUNT(r.id) > 0

        ORDER BY ROUND(CAST(AVG(r.rating) AS NUMERIC), 1) DESC, COUNT(r.id) DESC

        LIMIT 8

    """).fetchall()



    # Site-wide aggregate

    site_stats = db.execute("""

        SELECT COUNT(*) AS total_reviews,

               ROUND(CAST(AVG(rating) AS NUMERIC), 1) AS overall_rating

        FROM reviews

    """).fetchone()



    # Site-wide orders statistics

    # Delivered orders: base count of 8000 + actual orders in database (excluding pending payment and cancelled)

    db_orders_count = db.execute("SELECT COUNT(*) FROM orders WHERE status != 'Pending Payment' AND status != 'Cancelled'").fetchone()[0]

    total_delivered_count = 8000 + db_orders_count



    # States served: base count of 28 states + distinct states from orders

    db_states_count = db.execute("SELECT COUNT(DISTINCT state) FROM orders WHERE state IS NOT NULL AND state != ''").fetchone()[0]

    states_served = max(28, db_states_count)



    # Subscribers/Users count: 5000 base + real registered users

    db_user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    subscriber_count = 5000 + db_user_count



    db.close()

    return render_template(

        'index.html',

        bestsellers=bestsellers,

        carousel_slides=carousel_slides,

        categories=categories,

        product_reviews=product_reviews,

        site_stats=site_stats,

        total_delivered_count=total_delivered_count,

        states_served=states_served,

        subscriber_count=subscriber_count

    )





# ─────── Products ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/products')
def products():
    category = request.args.get('category', 'all').strip()

    categories_list = None
    products_list = None

    if redis_client:
        try:
            cached_cats = redis_client.get("nav_categories_list")
            cached_prods = redis_client.get("all_products_list")
            if cached_cats:
                categories_list = json.loads(cached_cats.decode('utf-8'))
            if cached_prods:
                products_list = json.loads(cached_prods.decode('utf-8'))
        except Exception as e:
            print(f"[REDIS] Products cache read error: {e}")

    db = None
    if not categories_list or not products_list:
        db = get_db()

    if not categories_list:
        all_categories = db.execute(
            "SELECT * FROM categories ORDER BY display_order ASC"
        ).fetchall()
        categories_list = [dict(c) for c in all_categories]
        if redis_client:
            try:
                redis_client.setex("nav_categories_list", 3600, json.dumps(categories_list))
            except Exception as e:
                print(f"[REDIS] Categories list write error: {e}")

    if not products_list:
        all_products = db.execute(
            "SELECT * FROM products ORDER BY category, name"
        ).fetchall()
        products_list = [dict(p) for p in all_products]
        if redis_client:
            try:
                redis_client.setex("all_products_list", 3600, json.dumps(products_list))
            except Exception as e:
                print(f"[REDIS] Products list write error: {e}")

    if db:
        db.close()

    # Enrich products with sub-categories dynamically
    for p in products_list:
        name_lower = p['name'].lower()
        if 'green tea' in name_lower:
            p['sub_category'] = 'Green Tea'
        elif 'black tea' in name_lower or 'tea' in name_lower:
            p['sub_category'] = 'Black Tea'
        elif 'garam masala' in name_lower:
            p['sub_category'] = 'Blend Spices'
        elif 'powder' in name_lower or 'turmeric' in name_lower or 'chilli' in name_lower or 'pepper' in name_lower or 'aamchur' in name_lower:
            p['sub_category'] = 'Ground Spices'
        elif 't-shirt' in name_lower or 'shirt' in name_lower:
            p['sub_category'] = 'Apparel'
        elif 'bag' in name_lower or 'tote' in name_lower:
            p['sub_category'] = 'Accessories'
        else:
            p['sub_category'] = 'Other'

    return render_template(
        'products.html',
        products=products_list,
        categories=categories_list,
        active_filter=category
    )





@app.route('/product/<id>')

def product_detail(id):

    db = get_db()

    product = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()

    if not product:

        db.close()

        flash("Product not found.", "error")

        return redirect(url_for('products'))

        

    # Get all images for this product

    images = db.execute("SELECT image_filename FROM product_images WHERE product_id = ?", (id,)).fetchall()

    image_list = [img['image_filename'] for img in images]

    

    # Fallback if no images are stored

    if not image_list and product['image_filename']:

        image_list = [product['image_filename']]

        

    # Get related/similar products (strictly of the same category, limit 5)

    related_products = db.execute(

        "SELECT * FROM products WHERE category = ? AND id != ? LIMIT 5",

        (product['category'], id)

    ).fetchall()

    

    related_products_list = [dict(p) for p in related_products]

        

    # Fetch reviews for this product

    reviews = db.execute("SELECT * FROM reviews WHERE product_id = ? ORDER BY created_at DESC", (id,)).fetchall()

    reviews_list = [dict(r) for r in reviews]

    

    # Calculate review stats

    total_reviews = len(reviews_list)

    avg_rating = 0.0

    rating_breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}

    if total_reviews > 0:

        total_stars = sum(r['rating'] for r in reviews_list)

        avg_rating = round(total_stars / total_reviews, 1)

        for r in reviews_list:

            r_val = r['rating']

            if r_val in rating_breakdown:

                rating_breakdown[r_val] += 1

                

    # Check wishlist

    wishlist = session.get('wishlist', [])

    in_wishlist = str(id) in [str(w) for w in wishlist]



    db.close()

    return render_template(

        'product_detail.html', 

        product=product, 

        images=image_list, 

        related_products=related_products_list,

        reviews=reviews_list,

        total_reviews=total_reviews,

        avg_rating=avg_rating,

        rating_breakdown=rating_breakdown,

        in_wishlist=in_wishlist

    )





@app.route('/product/<id>/review', methods=['POST'])

def add_review(id):

    if not session.get('user_id'):

        flash("You must be logged in to submit a review.", "error")

        return redirect(url_for('login', next=url_for('product_detail', id=id)))

        

    rating = request.form.get('rating')

    comment = request.form.get('comment', '').strip()

    user_name = session.get('user_name', 'Verified Buyer')

        

    if not rating:

        flash("Please select a star rating.", "error")

        return redirect(url_for('product_detail', id=id))

        

    try:

        rating_int = int(rating)

        if not (1 <= rating_int <= 5):

            raise ValueError()

    except ValueError:

        flash("Invalid rating value.", "error")

        return redirect(url_for('product_detail', id=id))

        

    db = get_db()

    # Handle review image upload (Max 5 MB)
    image_filename = None
    if 'review_image' in request.files:
        file = request.files['review_image']
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image format. Allowed formats: png, jpg, jpeg, gif, webp.", "error")
                return redirect(url_for('product_detail', id=id))
            
            # File size validation (Max 5 MB)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)  # Reset file pointer
            
            if size > 5 * 1024 * 1024:
                flash("Image size exceeds the maximum limit of 5 MB.", "error")
                return redirect(url_for('product_detail', id=id))
                
            filename = secure_filename(file.filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            file.save(filepath)
            image_filename = filename

    db.execute(
        "INSERT INTO reviews (product_id, user_name, rating, comment, image_filename) VALUES (?, ?, ?, ?, ?)",
        (id, user_name, rating_int, comment, image_filename)
    )
    db.commit()
    db.close()

    

    flash("Thank you! Your review has been submitted successfully.", "success")

    return redirect(url_for('product_detail', id=id))





# ─────── About ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/about')

def about():

    return render_template('about.html')





# ─────── Contact ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/contact')

def contact():

    return render_template('contact.html')





# ─────── Submit Enquiry (POST) ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/submit-enquiry', methods=['POST'])

def submit_enquiry():

    name = request.form.get('name', '').strip()

    email = request.form.get('email', '').strip()

    phone = request.form.get('phone', '').strip()

    product_interest = request.form.get('product_interest', '').strip()

    message = request.form.get('message', '').strip()



    if not name or not email:

        flash('Name and email are required.', 'error')

        return redirect(request.referrer or url_for('contact'))



    db = get_db()

    db.execute(

        "INSERT INTO enquiries (name, email, phone, product_interest, message) VALUES (?, ?, ?, ?, ?)",

        (name, email, phone, product_interest, message)

    )

    db.commit()

    db.close()



    flash('Thank you! Your enquiry has been received. We\'ll get back to you within 24 hours.', 'success')

    return redirect(request.referrer or url_for('contact'))


@app.route('/submit-proposal', methods=['POST'])
def submit_proposal():
    product_id = request.form.get('product_id', '').strip()
    product_name = request.form.get('product_name', '').strip()
    proposed_price = request.form.get('proposed_price', '').strip()
    proposed_qty = request.form.get('proposed_qty', '').strip()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not proposed_price or not proposed_qty:
        flash('Required fields are missing.', 'error')
        return redirect(request.referrer or url_for('home'))

    try:
        deal_value = float(proposed_price) * float(proposed_qty)
    except ValueError:
        deal_value = 0.0

    full_message = (
        f"💵 PROPOSED DEAL\n"
        f"Proposed Price: ₹{proposed_price} per unit\n"
        f"Proposed Quantity: {proposed_qty} units\n"
        f"Total Deal Value: ₹{deal_value:.2f}\n\n"
        f"Client Note:\n{message}"
    )
    product_interest = f"{product_name} (ID: {product_id}) [Deal Proposal]"

    db = get_db()
    db.execute(
        "INSERT INTO enquiries (name, email, phone, product_interest, message) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, product_interest, full_message)
    )
    db.commit()
    db.close()

    flash(f"Proposal submitted! We will review your offer of ₹{proposed_price} for {proposed_qty} units and contact you soon.", "success")
    return redirect(request.referrer or url_for('home'))


# ─────── Shopping Cart ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/cart')

def view_cart():

    cart = session.get('cart', {})

    cart_items = []

    subtotal = 0.0

    

    db = get_db()

    for prod_id, qty in cart.items():

        product = db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()

        if product:
            p_dict = dict(product)
            discount_percent = product['discount_percent'] if product['discount_percent'] else 0.0
            price_paid = product['price']
            if discount_percent > 0:
                price_paid = round(product['price'] * (1 - discount_percent / 100), 2)
            p_dict['price'] = price_paid
            p_dict['original_price'] = product['price']
            p_dict['quantity'] = qty
            p_dict['item_total'] = price_paid * qty
            subtotal += p_dict['item_total']
            cart_items.append(p_dict)

    db.close()

    

    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal)





@app.route('/cart/add/<product_id>', methods=['POST'])

def add_to_cart(product_id):

    qty = int(request.form.get('quantity', 1) or 1)

    if qty <= 0:

        qty = 1

        

    db = get_db()

    product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (product_id,)).fetchone()

    db.close()

    

    if not product:

        flash("Product not found.", "error")

        return redirect(url_for('products'))

        

    if product['stocks'] < qty:

        flash(f"Insufficient stock for {product['name']}. Only {product['stocks']} available.", "error")

        return redirect(request.referrer or url_for('products'))

        

    cart = session.get('cart', {})

    prod_id_str = str(product_id)

    cart[prod_id_str] = cart.get(prod_id_str, 0) + qty

    session['cart'] = cart

    session.modified = True



    # Buy Now: skip cart page, go directly to checkout

    if request.form.get('buy_now') == '1':

        flash(f"{product['name']} added. Complete your purchase below.", "success")

        return redirect(url_for('checkout'))



    flash(f"Added {qty} {product['name']} to cart.", "success")

    return redirect(url_for('view_cart'))





@app.route('/cart/update/<product_id>', methods=['POST'])

def update_cart(product_id):

    qty = int(request.form.get('quantity', 1) or 1)

    cart = session.get('cart', {})

    prod_id_str = str(product_id)

    

    if qty <= 0:

        cart.pop(prod_id_str, None)

        flash("Item removed from cart.", "success")

    else:

        db = get_db()

        product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (product_id,)).fetchone()

        db.close()

        

        if product and product['stocks'] < qty:

            flash(f"Cannot update quantity. Only {product['stocks']} units in stock.", "error")

            return redirect(url_for('view_cart'))

            

        cart[prod_id_str] = qty

        flash("Cart updated.", "success")

        

    session['cart'] = cart

    session.modified = True

    return redirect(url_for('view_cart'))





@app.route('/cart/remove/<product_id>', methods=['POST'])

def remove_from_cart(product_id):

    cart = session.get('cart', {})

    cart.pop(str(product_id), None)

    session['cart'] = cart

    session.modified = True

    flash("Item removed from cart.", "success")

    return redirect(url_for('view_cart'))





@app.route('/wishlist/toggle/<product_id>', methods=['POST'])

def toggle_wishlist(product_id):

    """Add or remove a product from the session wishlist."""

    if 'user_id' not in session:

        flash("Please log in to save items to your wishlist.", "error")

        return redirect(url_for('login', next=request.referrer or url_for('products')))



    wishlist = session.get('wishlist', [])

    prod_str = str(product_id)



    if prod_str in [str(w) for w in wishlist]:

        wishlist = [w for w in wishlist if str(w) != prod_str]

        flash("Removed from your wishlist.", "info")

    else:

        wishlist.append(prod_str)

        flash("Added to your wishlist! ❤️", "success")



    session['wishlist'] = wishlist

    session.modified = True

    return redirect(request.referrer or url_for('product_detail', id=product_id))





@app.route('/api/calculate-shipping', methods=['POST'])
def calculate_shipping():
    """AJAX endpoint: calculate shipping charges based on location (state) and cart products."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please log in first.'}), 401
    
    data = request.get_json() or {}
    state_input = data.get('state', '').strip()
    
    if not state_input:
        return jsonify({'success': False, 'message': 'State is required.'}), 400
        
    db = get_db()
    
    # 1. Location-Wise base charge
    state_row = db.execute(
        "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = ?",
        (state_input.upper(),)
    ).fetchone()
    
    if state_row:
        location_charge = float(state_row['charge'])
    else:
        # Fall back to Default rate
        default_row = db.execute(
            "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = 'DEFAULT'"
        ).fetchone()
        location_charge = float(default_row['charge']) if default_row else 60.0
        
    # 2. Product-Wise additional charge
    cart = session.get('cart', {})
    product_charge = 0.0
    
    if cart:
        product_ids = [int(pid) for pid in cart.keys() if pid.isdigit()]
        if product_ids:
            placeholders = ','.join('?' for _ in product_ids)
            products_rows = db.execute(
                f"SELECT id, shipping_charge FROM products WHERE id IN ({placeholders})",
                product_ids
            ).fetchall()
            
            prod_charge_map = {row['id']: float(row['shipping_charge'] or 0.0) for row in products_rows}
            for pid, qty in cart.items():
                if pid.isdigit() and int(pid) in prod_charge_map:
                    product_charge += prod_charge_map[int(pid)] * int(qty)
                    
    db.close()
    
    total_shipping = location_charge + product_charge
    return jsonify({
        'success': True,
        'location_charge': location_charge,
        'product_charge': product_charge,
        'total_shipping': total_shipping
    })

@app.route('/admin/shipping/add', methods=['POST'])
@admin_required
def admin_add_shipping():
    state = request.form.get('state', '').strip()
    charge = float(request.form.get('charge', 0.0) or 0.0)
    
    if not state:
        flash('State name is required.', 'error')
        return redirect(url_for('admin_dashboard') + '#shipping-tab')
        
    db = get_db()
    try:
        db.execute("INSERT INTO location_shipping_charges (state, charge) VALUES (?, ?)", (state, charge))
        db.commit()
        flash(f'Shipping rate for {state} added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Shipping rate for {state} already exists.', 'error')
    finally:
        db.close()
        
    return redirect(url_for('admin_dashboard') + '#shipping-tab')

@app.route('/admin/shipping/edit/<int:id>', methods=['POST'])
@admin_required
def admin_edit_shipping(id):
    state = request.form.get('state', '').strip()
    charge = float(request.form.get('charge', 0.0) or 0.0)
    
    if not state:
        flash('State name is required.', 'error')
        return redirect(url_for('admin_dashboard') + '#shipping-tab')
        
    db = get_db()
    try:
        db.execute(
            "UPDATE location_shipping_charges SET state = ?, charge = ? WHERE id = ?",
            (state, charge, id)
        )
        db.commit()
        flash('Shipping rate updated successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Shipping rate for {state} already exists.', 'error')
    finally:
        db.close()
        
    return redirect(url_for('admin_dashboard') + '#shipping-tab')

@app.route('/admin/shipping/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_shipping(id):
    db = get_db()
    db.execute("DELETE FROM location_shipping_charges WHERE id = ?", (id,))
    db.commit()
    db.close()
    flash('Shipping rate deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#shipping-tab')


# ─────── Checkout & Ordering ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/api/validate-promo', methods=['POST'])

def validate_promo():

    """AJAX endpoint: validate a promo code against the current cart subtotal."""

    if 'user_id' not in session:

        return jsonify({'valid': False, 'message': 'Please log in first.'})

    data = request.get_json() or {}

    code = data.get('code', '').strip().upper()

    subtotal = float(data.get('subtotal', 0))

    if not code:

        return jsonify({'valid': False, 'message': 'Enter a promo code.'})

    db = get_db()

    promo = db.execute(

        "SELECT * FROM promo_codes WHERE UPPER(code) = ? AND is_active = 1",

        (code,)

    ).fetchone()

    db.close()

    if not promo:

        return jsonify({'valid': False, 'message': 'Invalid or inactive promo code.'})

    # Check expiry

    if promo['expires_at']:

        from datetime import datetime as dt

        try:

            exp = dt.fromisoformat(promo['expires_at'])

            if dt.now() > exp:

                return jsonify({'valid': False, 'message': 'This promo code has expired.'})

        except Exception:

            pass

    # Check max uses

    if promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']:

        return jsonify({'valid': False, 'message': 'This promo code has reached its usage limit.'})

    # Check min order

    if subtotal < promo['min_order_amount']:

        return jsonify({

            'valid': False,

            'message': f"Minimum order ₹{promo['min_order_amount']:.0f} required for this code."

        })

    # Calculate discount

    if promo['discount_type'] == 'percent':

        discount_amount = round(subtotal * promo['discount_value'] / 100, 2)

    else:

        discount_amount = min(round(promo['discount_value'], 2), subtotal)

    final_total = round(subtotal - discount_amount, 2)

    return jsonify({

        'valid': True,

        'code': promo['code'],

        'discount_type': promo['discount_type'],

        'discount_value': promo['discount_value'],

        'discount_amount': discount_amount,

        'final_total': final_total,

        'message': f"Code applied! You save ₹{discount_amount:.2f}"

    })





@app.route('/profile')

def profile():

    if 'user_id' not in session:

        flash("Please log in to view your profile.", "error")

        return redirect(url_for('login', next=request.url))

        

    db = get_db()

    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    

    if not user:

        db.close()

        session.clear()

        flash("Your session is invalid. Please log in again.", "error")

        return redirect(url_for('login'))



    proposals = db.execute("SELECT * FROM enquiries WHERE email = ? ORDER BY created_at DESC", (user['email'],)).fetchall()

    db.close()

    return render_template('profile.html', user=user, proposals=proposals)





@app.route('/profile/update-info', methods=['POST'])

def profile_update_info():

    if 'user_id' not in session:

        return redirect(url_for('login'))

        

    full_name = request.form.get('full_name', '').strip()

    phone = request.form.get('phone', '').strip()

    shipping_address = request.form.get('shipping_address', '').strip()

    city = request.form.get('city', '').strip()

    state = request.form.get('state', '').strip()

    zip_code = request.form.get('zip_code', '').strip()

    

    if not full_name:

        flash("Full Name is required.", "error")

        return redirect(url_for('profile'))

        

    db = get_db()

    db.execute(

        """

        UPDATE users 

        SET full_name = ?, phone = ?, shipping_address = ?, city = ?, state = ?, zip_code = ?

        WHERE id = ?

        """,

        (full_name, phone, shipping_address, city, state, zip_code, session['user_id'])

    )

    db.commit()

    db.close()

    

    session['user_name'] = full_name

    flash("Profile information updated successfully!", "success")

    return redirect(url_for('profile'))





@app.route('/profile/change-password', methods=['POST'])

def profile_change_password():

    if 'user_id' not in session:

        return redirect(url_for('login'))

        

    current_password = request.form.get('current_password', '')

    new_password = request.form.get('new_password', '')

    confirm_password = request.form.get('confirm_password', '')

    

    if not current_password or not new_password or not confirm_password:

        flash("All password fields are required.", "error")

        return redirect(url_for('profile'))

        

    if new_password != confirm_password:

        flash("New password and confirm password do not match.", "error")

        return redirect(url_for('profile'))

        

    db = get_db()

    user = db.execute("SELECT password_hash FROM users WHERE id = ?", (session['user_id'],)).fetchone()

    

    if not user:

        db.close()

        session.clear()

        flash("Your session is invalid. Please log in again.", "error")

        return redirect(url_for('login'))

        

    if hash_password(current_password) != user['password_hash']:

        db.close()

        flash("Incorrect current password.", "error")

        return redirect(url_for('profile'))

        

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), session['user_id']))

    db.commit()

    db.close()

    

    flash("Password updated successfully!", "success")

    return redirect(url_for('profile'))





@app.route('/checkout')

def checkout():

    if 'user_id' not in session:

        flash("Please log in to proceed to checkout.", "error")

        return redirect(url_for('login', next=request.url))

        

    cart = session.get('cart', {})

    if not cart:

        flash("Your cart is empty.", "error")

        return redirect(url_for('products'))

        

    cart_items = []

    subtotal = 0.0

    db = get_db()

    for prod_id, qty in cart.items():

        product = db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()

        if product:
            p_dict = dict(product)
            discount_percent = product['discount_percent'] if product['discount_percent'] else 0.0
            price_paid = product['price']
            if discount_percent > 0:
                price_paid = round(product['price'] * (1 - discount_percent / 100), 2)
            p_dict['price'] = price_paid
            p_dict['original_price'] = product['price']
            p_dict['quantity'] = qty
            p_dict['item_total'] = price_paid * qty
            subtotal += p_dict['item_total']
            cart_items.append(p_dict)

    # Fetch user info for address pre-filling

    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    db.close()
    
    return render_template('checkout.html', cart_items=cart_items, subtotal=subtotal, user=user)





@app.route('/checkout/submit', methods=['POST'])

def checkout_submit():

    if 'user_id' not in session:

        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 401

        

    cart = session.get('cart', {})

    if not cart:

        return jsonify({"success": False, "message": "Your cart is empty."}), 400

        

    shipping_address = request.form.get('address', '').strip()

    city = request.form.get('city', '').strip()

    state = request.form.get('state', '').strip()

    zip_code = request.form.get('zip', '').strip()

    contact_name = request.form.get('contact_name', '').strip()

    contact_email = request.form.get('contact_email', '').strip()

    contact_phone = request.form.get('contact_phone', '').strip()

    payment_method = request.form.get('payment_method', 'UPI').strip()

    promo_code_input = request.form.get('promo_code', '').strip().upper()

    discount_amount_input = float(request.form.get('discount_amount', 0) or 0)



    if not shipping_address or not city or not state or not zip_code or not contact_name or not contact_email or not contact_phone:

        return jsonify({"success": False, "message": "Please fill in all shipping and contact details."}), 400



    db = get_db()

    try:

        # Check stock and calculate total amount

        total_amount = 0.0

        order_items_to_create = []

        for prod_id, qty in cart.items():

            product = db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()

            if not product:

                return jsonify({"success": False, "message": "One of the products in your cart is no longer available."}), 400



            if product['stocks'] < qty:

                return jsonify({"success": False, "message": f"Insufficient stock for {product['name']}. Only {product['stocks']} available."}), 400



            discount_percent = product['discount_percent'] if product['discount_percent'] else 0.0
            price_paid = product['price']
            if discount_percent > 0:
                price_paid = round(product['price'] * (1 - discount_percent / 100), 2)

            total_amount += price_paid * qty

            order_items_to_create.append({
                'product_id': product['id'],
                'product_name': product['name'],
                'quantity': qty,
                'price': price_paid,
                'original_price': product['price'],
                'discount_percent': discount_percent
            })



        # Validate and apply promo code

        applied_promo = None

        final_discount = 0.0

        if promo_code_input:

            promo = db.execute(

                "SELECT * FROM promo_codes WHERE UPPER(code) = ? AND is_active = 1",

                (promo_code_input,)

            ).fetchone()

            if promo:

                # Revalidate server-side

                is_expired = False

                if promo['expires_at']:

                    try:

                        exp = datetime.fromisoformat(promo['expires_at'])

                        is_expired = datetime.utcnow() > exp

                    except Exception:

                        pass

                max_hit = promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']

                min_ok = total_amount >= promo['min_order_amount']

                if not is_expired and not max_hit and min_ok:

                    if promo['discount_type'] == 'percent':

                        final_discount = round(total_amount * promo['discount_value'] / 100, 2)

                    else:

                        final_discount = min(round(promo['discount_value'], 2), total_amount)

                    applied_promo = promo



        # Secure server-side calculation of shipping charges
        state_row = db.execute(
            "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = ?",
            (state.upper(),)
        ).fetchone()
        
        if state_row:
            location_charge = float(state_row['charge'])
        else:
            default_row = db.execute(
                "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = 'DEFAULT'"
            ).fetchone()
            location_charge = float(default_row['charge']) if default_row else 60.0

        product_shipping_total = 0.0
        for prod_id, qty in cart.items():
            product_sh = db.execute("SELECT shipping_charge FROM products WHERE id = ?", (prod_id,)).fetchone()
            if product_sh:
                product_shipping_total += float(product_sh['shipping_charge'] or 0.0) * int(qty)
                
        final_shipping_charge = location_charge + product_shipping_total
        final_total = round(total_amount - final_discount + final_shipping_charge, 2)

        order_number = generate_order_number()

        if payment_method == 'COD':

            # Cash on Delivery: Process and place order immediately

            cursor = db.execute(

                """INSERT INTO orders

                   (user_id, total_amount, shipping_address, city, state, zip_code,

                    payment_method, status, discount_amount, promo_code, order_number,

                    contact_name, contact_email, contact_phone, razorpay_order_id, shipping_charge)

                   VALUES (?, ?, ?, ?, ?, ?, 'COD', 'Processing', ?, ?, ?, ?, ?, ?, 'COD', ?)""",

                (session['user_id'], final_total, shipping_address, city, state, zip_code,

                 final_discount, applied_promo['code'] if applied_promo else '',

                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)

            )

            order_id = cursor.lastrowid



            # Create order items & decrement stock levels

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )

                db.execute(

                    "UPDATE products SET stocks = stocks - ? WHERE id = ?",

                    (item['quantity'], item['product_id'])

                )



            # Increment promo code usage if applied

            if applied_promo:

                db.execute(

                    "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",

                    (applied_promo['code'].upper(),)

                )



            # Clear cart session

            session.pop('cart', None)

            session.modified = True



            db.commit()



            # Send order confirmation email

            try:

                queue_order_confirmation_email(

                    contact_email, contact_name, order_number, final_total,

                    f"{shipping_address}, {city}, {state} - {zip_code}",

                    order_items_to_create

                )

            except Exception as mail_err:

                print(f"[MAIL] Failed to send order confirmation email: {str(mail_err)}")



            return jsonify({

                "success": True,

                "cod": True,

                "redirect_url": url_for('my_orders')

            })



        elif payment_method == 'PayPal':

            # PayPal Payment: Create in Pending Payment state and generate PayPal Order

            cursor = db.execute(
                """INSERT INTO orders
                   (user_id, total_amount, shipping_address, city, state, zip_code,
                    payment_method, status, discount_amount, promo_code, order_number,
                    contact_name, contact_email, contact_phone, paypal_order_id, shipping_charge)
                   VALUES (?, ?, ?, ?, ?, ?, 'PayPal', 'Pending Payment', ?, ?, ?, ?, ?, ?, '', ?)""",
                (session['user_id'], final_total, shipping_address, city, state, zip_code,
                 final_discount, applied_promo['code'] if applied_promo else '',
                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)
            )

            order_id = cursor.lastrowid

            # Create order items

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )

            # Generate PayPal Order ID
            token = get_paypal_access_token()
            paypal_ord_id = None
            usd_total = round(final_total * PAYPAL_EXCHANGE_RATE, 2)

            if token:
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    }
                    payload = {
                        "intent": "CAPTURE",
                        "purchase_units": [
                            {
                                "reference_id": order_number,
                                "amount": {
                                    "currency_code": "USD",
                                    "value": f"{usd_total:.2f}"
                                },
                                "description": f"Order {order_number} from The Saveur"
                            }
                        ]
                    }
                    url = f"{get_paypal_api_base()}/v2/checkout/orders"
                    res = requests.post(url, headers=headers, json=payload, timeout=10)
                    if res.status_code in (200, 201):
                        paypal_ord_id = res.json().get('id')
                    else:
                        print(f"[PAYPAL] Order creation failed: {res.status_code} - {res.text}")
                except Exception as py_err:
                    print(f"[PAYPAL] Order API error: {str(py_err)}")

            if not paypal_ord_id:
                paypal_ord_id = f"MOCK_PAYPAL_ORD_{order_number}"

            db.execute(
                "UPDATE orders SET paypal_order_id = ? WHERE id = ?",
                (paypal_ord_id, order_id)
            )

            db.commit()

            return jsonify({
                "success": True,
                "paypal": True,
                "order_id": order_id,
                "order_number": order_number,
                "paypal_order_id": paypal_ord_id,
                "amount_usd": f"{usd_total:.2f}",
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            })

        else:

            # Online Payment: Create in Pending Payment state and generate Razorpay Order

            cursor = db.execute(
                """INSERT INTO orders
                   (user_id, total_amount, shipping_address, city, state, zip_code,
                    payment_method, status, discount_amount, promo_code, order_number,
                    contact_name, contact_email, contact_phone, razorpay_order_id, shipping_charge)
                   VALUES (?, ?, ?, ?, ?, ?, 'Online', 'Pending Payment', ?, ?, ?, ?, ?, ?, '', ?)""",
                (session['user_id'], final_total, shipping_address, city, state, zip_code,
                 final_discount, applied_promo['code'] if applied_promo else '',
                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)
            )

            order_id = cursor.lastrowid



            # Create order items

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )



            # Generate Razorpay Order

            rz_client = get_razorpay_client()

            rz_order_id = None

            

            if IS_REAL_MODE and not rz_client:

                raise Exception("Razorpay client is not configured. Real Mode is enabled.")

                

            if rz_client:

                try:

                    amount_paise = int(final_total * 100)

                    notes = {

                        "order_number": order_number,

                        "contact_name": contact_name,

                        "contact_email": contact_email

                    }

                    rz_order = rz_client.order.create(data={

                        "amount": amount_paise,

                        "currency": "INR",

                        "receipt": f"rcpt_{order_number}",

                        "notes": notes

                    })

                    rz_order_id = rz_order.get('id')

                except Exception as rz_err:

                    print(f"[RAZORPAY] Order creation error: {str(rz_err)}")

                    if IS_REAL_MODE:

                        raise Exception(f"Razorpay order creation failed: {str(rz_err)}")



            if not rz_order_id:

                if IS_REAL_MODE:

                    raise Exception("Unable to generate Razorpay Order ID.")

                rz_order_id = f"MOCK_ORD_{order_number}"



            db.execute(

                "UPDATE orders SET razorpay_order_id = ? WHERE id = ?",

                (rz_order_id, order_id)

            )



            db.commit()

            

            return jsonify({

                "success": True,

                "order_id": order_id,

                "order_number": order_number,

                "razorpay_order_id": rz_order_id,

                "razorpay_key_id": RAZORPAY_KEY_ID,

                "amount": int(final_total * 100),

                "contact_name": contact_name,

                "contact_email": contact_email,

                "contact_phone": contact_phone

            })

        

    except Exception as e:

        db.rollback()

        return jsonify({"success": False, "message": f"An error occurred: {str(e)}"}), 500

    finally:

        db.close()





@app.route('/checkout/verify', methods=['POST'])

def checkout_verify():

    if 'user_id' not in session:

        return jsonify({"success": False, "message": "Unauthorized access."}), 401



    order_id = request.form.get('order_id')

    razorpay_payment_id = request.form.get('razorpay_payment_id', '').strip()

    razorpay_order_id = request.form.get('razorpay_order_id', '').strip()

    razorpay_signature = request.form.get('razorpay_signature', '').strip()

    is_mock = request.form.get('is_mock', 'false').lower() == 'true'



    if not order_id:

        return jsonify({"success": False, "message": "Missing order details."}), 400



    db = get_db()

    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, session['user_id'])).fetchone()

    if not order:

        db.close()

        return jsonify({"success": False, "message": "Order not found."}), 404



    if order['status'] != 'Pending Payment':

        db.close()

        return jsonify({"success": False, "message": "Order already processed."}), 400



    # Signature verification

    signature_valid = False

    if is_mock and not IS_REAL_MODE:

        signature_valid = True

    else:

        # Real verification using Razorpay SDK

        rz_client = get_razorpay_client()

        if rz_client:

            try:

                rz_client.utility.verify_payment_signature({

                    'razorpay_order_id': razorpay_order_id,

                    'razorpay_payment_id': razorpay_payment_id,

                    'razorpay_signature': razorpay_signature

                })

                signature_valid = True

            except Exception as e:

                print(f"[RAZORPAY] Signature verification failed: {str(e)}")



    if not signature_valid:

        db.close()

        return jsonify({"success": False, "message": "Payment verification failed. Invalid signature."}), 400



    try:

        # Fetch order items to update stock

        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()

        

        # Check stock again for safety

        for item in order_items:

            product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (item['product_id'],)).fetchone()

            if not product or product['stocks'] < item['quantity']:

                db.close()

                return jsonify({"success": False, "message": f"Insufficient stock for {product['name'] if product else 'product'}."}), 400



        # Decrement product stock levels

        for item in order_items:

            db.execute(

                "UPDATE products SET stocks = stocks - ? WHERE id = ?",

                (item['quantity'], item['product_id'])

            )



        # Update order details and status

        db.execute(

            """UPDATE orders 

               SET status = 'Processing', razorpay_payment_id = ?, razorpay_signature = ? 

               WHERE id = ?""",

            (razorpay_payment_id if (not is_mock or IS_REAL_MODE) else 'MOCK_PAY_' + razorpay_order_id, 

             razorpay_signature if (not is_mock or IS_REAL_MODE) else 'MOCK_SIG', 

             order_id)

        )



        # Increment promo code usage if applied

        if order['promo_code']:

            db.execute(

                "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",

                (order['promo_code'].upper(),)

            )



        db.commit()



        # Send confirmation email

        try:

            items_list = []

            for item in order_items:

                prod = db.execute("SELECT name FROM products WHERE id = ?", (item['product_id'],)).fetchone()

                items_list.append({

                    'product_name': prod['name'] if prod else 'Product',

                    'quantity': item['quantity'],

                    'price': item['price']

                })

            

            queue_order_confirmation_email(

                order['contact_email'],

                order['contact_name'],

                order['order_number'],

                order['total_amount'],

                f"{order['shipping_address']}, {order['city']}, {order['state']} – {order['zip_code']}",

                items_list

            )

        except Exception as mail_err:

            print(f"[MAIL ALERT ERROR] Failed to send order confirmation email: {str(mail_err)}")



        # Clear cart session

        session['cart'] = {}

        session.modified = True



        db.close()

        flash(f"Payment successful! Order {order['order_number']} is now being processed. 🎉", "success")

        return jsonify({"success": True, "redirect_url": url_for('my_orders')})

    except Exception as e:

        db.rollback()

        db.close()

        return jsonify({"success": False, "message": f"Error updating order: {str(e)}"}), 500





@app.route('/checkout/verify-paypal', methods=['POST'])

def checkout_verify_paypal():

    if 'user_id' not in session:

        return jsonify({"success": False, "message": "Unauthorized access."}), 401



    order_id = request.form.get('order_id')

    paypal_order_id = request.form.get('paypal_order_id', '').strip()

    is_mock = "MOCK_PAYPAL_ORD" in paypal_order_id or not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)



    if not order_id:

        return jsonify({"success": False, "message": "Missing order details."}), 400



    db = get_db()

    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, session['user_id'])).fetchone()



    if not order:

        db.close()

        return jsonify({"success": False, "message": "Order not found."}), 404



    if order['status'] != 'Pending Payment':

        db.close()

        return jsonify({"success": False, "message": "Order already processed."}), 400



    paypal_payment_id = None

    capture_success = False



    if is_mock:

        capture_success = True

        paypal_payment_id = f"MOCK_PAY_ID_{order['order_number']}"

    else:

        token = get_paypal_access_token()

        if token:

            try:

                headers = {

                    "Content-Type": "application/json",

                    "Authorization": f"Bearer {token}"

                }

                url = f"{get_paypal_api_base()}/v2/checkout/orders/{paypal_order_id}/capture"

                res = requests.post(url, headers=headers, timeout=10)

                if res.status_code in (200, 201):

                    res_data = res.json()

                    if res_data.get('status') == 'COMPLETED':

                        capture_success = True

                        try:

                            purchase_units = res_data.get('purchase_units', [])

                            payments = purchase_units[0].get('payments', {})

                            captures = payments.get('captures', [])

                            paypal_payment_id = captures[0].get('id')

                        except Exception:

                            paypal_payment_id = f"PAY_ID_{order['order_number']}"

                else:

                    print(f"[PAYPAL] Capture API failed: {res.status_code} - {res.text}")

            except Exception as e:

                print(f"[PAYPAL] Capture error: {str(e)}")



    if not capture_success:

        db.close()

        return jsonify({"success": False, "message": "PayPal payment capture failed."}), 400



    try:

        # Fetch order items to update stock

        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()



        # Check stock again for safety

        for item in order_items:

            product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (item['product_id'],)).fetchone()

            if not product or product['stocks'] < item['quantity']:

                db.close()

                return jsonify({"success": False, "message": f"Insufficient stock for {product['name'] if product else 'product'}."}), 400



        # Decrement product stock levels

        for item in order_items:

            db.execute(

                "UPDATE products SET stocks = stocks - ? WHERE id = ?",

                (item['quantity'], item['product_id'])

            )



        # Update order details and status

        db.execute(

            """UPDATE orders 

               SET status = 'Processing', paypal_payment_id = ? 

               WHERE id = ?""",

            (paypal_payment_id, order_id)

        )



        # Increment promo code usage if applied

        if order['promo_code']:

            db.execute(

                "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",

                (order['promo_code'].upper(),)

            )



        db.commit()



        # Send confirmation email

        try:

            items_list = []

            for item in order_items:

                prod = db.execute("SELECT name FROM products WHERE id = ?", (item['product_id'],)).fetchone()

                items_list.append({

                    'product_name': prod['name'] if prod else 'Product',

                    'quantity': item['quantity'],

                    'price': item['price']

                })

            

            queue_order_confirmation_email(

                order['contact_email'],

                order['contact_name'],

                order['order_number'],

                order['total_amount'],

                f"{order['shipping_address']}, {order['city']}, {order['state']} – {order['zip_code']}",

                items_list

            )

        except Exception as mail_err:

            print(f"[MAIL ALERT ERROR] Failed to send order confirmation email: {str(mail_err)}")



        # Clear cart session

        session['cart'] = {}

        session.modified = True



        db.close()

        flash(f"Payment successful! Order {order['order_number']} is now being processed. 🎉", "success")

        return jsonify({"success": True, "redirect_url": url_for('my_orders')})



    except Exception as e:

        db.rollback()

        db.close()

        return jsonify({"success": False, "message": f"Error updating order: {str(e)}"}), 500







@app.route('/my-orders')

def my_orders():

    if 'user_id' not in session:

        flash("Please log in to view your orders.", "error")

        return redirect(url_for('login'))

        

    db = get_db()

    orders_raw = db.execute(

        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", 

        (session['user_id'],)

    ).fetchall()

    

    orders_list = []

    for order in orders_raw:

        o_dict = dict(order)

        items = db.execute(

            """

            SELECT oi.*, p.name as product_name, p.image_filename 

            FROM order_items oi

            JOIN products p ON oi.product_id = p.id

            WHERE oi.order_id = ?

            """,

            (order['id'],)

        ).fetchall()

        o_dict['items'] = [dict(item) for item in items]

        orders_list.append(o_dict)

        

    db.close()

    return render_template('my_orders.html', orders=orders_list)





@app.route('/track-order/<int:order_id>')

def track_order(order_id):

    """Public live tracking page for customers."""

    db = get_db()

    order = db.execute(

        """

        SELECT o.*, u.full_name as customer_name

        FROM orders o

        JOIN users u ON o.user_id = u.id

        WHERE o.id = ?

        """,

        (order_id,)

    ).fetchone()

    

    if not order:

        db.close()

        return "Order not found", 404

        

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

    return render_template('track_order.html', order=order, items=items)





# ─────── Auth ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/signup', methods=['GET', 'POST'])

def signup():

    if 'user_id' in session:

        return redirect(url_for('home'))



    if request.method == 'POST':

        full_name = request.form.get('full_name', '').strip()

        email = request.form.get('email', '').strip().lower()

        password = request.form.get('password', '')

        confirm_password = request.form.get('confirm_password', '')

        terms = request.form.get('terms')



        if not full_name or not email or not password:

            flash('All fields are required.', 'error')

            return render_template('signup.html')



        if not terms:

            flash('You must agree to the Terms of Service and Privacy Policy.', 'error')

            return render_template('signup.html')



        if len(password) < 6:

            flash('Password must be at least 6 characters.', 'error')

            return render_template('signup.html')



        if password != confirm_password:

            flash('Passwords do not match.', 'error')

            return render_template('signup.html')



        db = get_db()

        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()

        if existing:

            db.close()

            flash('An account with this email already exists. Please log in.', 'error')

            return render_template('signup.html')



        # Generate OTP and store pending signup in email_verifications
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'signup', ?)",
            (email, otp, expires_at)
        )
        db.commit()
        db.close()

        # Save signup OTP to session for stateless Vercel compatibility
        session['signup_otp'] = otp
        session['signup_otp_expires_at'] = expires_at

        # Store pending user data in session (not created yet)
        session['otp_email'] = email

        session['otp_purpose'] = 'signup'

        session['pending_user'] = {

            'full_name': full_name,

            'email': email,

            'password_hash': hash_password(password)

        }



        if not queue_otp_email(email, otp, purpose='signup'):

            flash('Failed to send OTP email. Please check SMTP configuration and try again.', 'error')

            return render_template('signup.html')



        flash('A 6-digit verification code has been sent to your email. Please verify to complete registration.', 'success')

        return redirect(url_for('verify_otp'))



    return render_template('signup.html')





@app.route('/login', methods=['GET', 'POST'])

def login():

    if 'user_id' in session:

        next_url = request.args.get('next') or url_for('home')

        return redirect(next_url)



    next_url = request.args.get('next', '')



    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()

        password = request.form.get('password', '')

        next_url = request.form.get('next', '') or url_for('home')



        if not email or not password:

            flash('Email and password are required.', 'error')

            return render_template('login.html', next=next_url)



        db = get_db()

        user = db.execute(

            "SELECT * FROM users WHERE email = ? AND password_hash = ?",

            (email, hash_password(password))

        ).fetchone()

        db.close()



        if user:

            if bool(user['is_admin']):

                # Generate OTP and store in email_verifications

                otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

                expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

                

                db = get_db()

                db.execute(

                    "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'admin_login', ?)",

                    (user['email'], otp, expires_at)

                )

                db.commit()

                db.close()

                

                # Save admin login OTP to session for stateless Vercel compatibility
                session['admin_login_otp'] = otp
                session['admin_login_otp_expires_at'] = expires_at

                session['otp_email'] = user['email']
                session['otp_purpose'] = 'admin_login'

                session['pending_admin_user'] = {

                    'id': user['id'],

                    'full_name': user['full_name'],

                    'email': user['email'],

                    'next': next_url

                }

                

                if not queue_otp_email(user['email'], otp, purpose='admin_login'):

                    print(f"[ERROR] Failed to send admin login OTP to {user['email']}")

                

                flash('A 6-digit verification code has been sent to your email. Please verify to log in as administrator.', 'success')

                return redirect(url_for('verify_otp'))

            else:
                session.permanent = True
                session['user_id'] = user['id']
                session['user_name'] = user['full_name']
                session['is_admin'] = False



                # Send login alert email

                queue_login_alert_email(user['email'], user['full_name'])



                flash(f'Welcome back, {user["full_name"]}!', 'success')

                return redirect(next_url if next_url else url_for('home'))

        else:

            flash('Invalid email or password. Please try again.', 'error')

            return render_template('login.html', next=next_url)



    return render_template('login.html', next=next_url)





@app.route('/logout')

def logout():

    user_name = session.get('user_name', 'User')

    session.clear()

    flash(f'Goodbye, {user_name}! You have been logged out.', 'success')

    return redirect(url_for('home'))





@app.route('/forgot-password', methods=['GET', 'POST'])

def forgot_password():

    if 'user_id' in session:

        return redirect(url_for('home'))



    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()

        if not email:

            flash('Email address is required.', 'error')

            return render_template('forgot_password.html')



        db = get_db()

        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()



        if not user:

            db.close()

            flash('No account found with that email address.', 'error')

            return render_template('forgot_password.html')



        # Generate a 6-digit OTP

        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()



        db.execute(

            "INSERT INTO password_resets (email, otp, expires_at) VALUES (?, ?, ?)",

            (email, otp, expires_at)

        )

        db.commit()

        db.close()



        # Save reset OTP to session for stateless Vercel compatibility
        session['reset_otp'] = otp
        session['reset_otp_expires_at'] = expires_at

        session['otp_email'] = email
        session['otp_purpose'] = 'reset'

        session['reset_email'] = email  # keep for backward compat with reset_password route



        if not queue_otp_email(email, otp, purpose='reset'):

            flash('Failed to send OTP email. Please ensure SMTP is configured correctly in your .env file.', 'error')

            return render_template('forgot_password.html')



        flash('A 6-digit OTP has been sent to your email address.', 'success')

        return redirect(url_for('verify_otp'))



    return render_template('forgot_password.html')





@app.route('/verify-otp', methods=['GET', 'POST'])

def verify_otp():

    if 'user_id' in session:

        return redirect(url_for('home'))



    email = session.get('otp_email') or session.get('reset_email')

    purpose = session.get('otp_purpose', 'reset')  # 'signup' or 'reset'



    if not email:

        flash('Session expired. Please start again.', 'error')

        return redirect(url_for('signup') if purpose == 'signup' else url_for('forgot_password'))



    if request.method == 'POST':

        otp_digits = [request.form.get(f'otp-{i}', '').strip() for i in range(1, 7)]

        entered_otp = ''.join(otp_digits)

        if not entered_otp:

            entered_otp = request.form.get('otp', '').strip()



        if not entered_otp or len(entered_otp) != 6:

            flash('Please enter the full 6-digit OTP code.', 'error')

            return render_template('verify_otp.html', purpose=purpose, email=email)



        db = get_db()



        if purpose == 'signup':
            # Check session fallback first for serverless Vercel compatibility
            session_otp = session.get('signup_otp')
            session_expiry_str = session.get('signup_otp_expires_at')
            verified = False
            
            if session_otp and session_expiry_str:
                try:
                    exp = datetime.fromisoformat(session_expiry_str)
                    if session_otp == entered_otp and datetime.utcnow() <= exp:
                        verified = True
                except Exception:
                    pass
            
            if not verified:
                otp_row = db.execute(
                    "SELECT * FROM email_verifications WHERE email = ? AND purpose = 'signup' AND used = 0 ORDER BY id DESC LIMIT 1",
                    (email,)
                ).fetchone()

                if not otp_row:
                    db.close()
                    flash('No active OTP found. Please sign up again.', 'error')
                    return redirect(url_for('signup'))

                try:
                    expires_at = datetime.fromisoformat(otp_row['expires_at'])
                except Exception:
                    expires_at = datetime.utcnow()

                if otp_row['otp'] != entered_otp:
                    db.close()
                    flash('Invalid OTP code. Please check and try again.', 'error')
                    return render_template('verify_otp.html', purpose=purpose, email=email)

                if datetime.utcnow() > expires_at:
                    db.close()
                    flash('This OTP has expired. Please sign up again.', 'error')
                    return redirect(url_for('signup'))

                # Mark OTP used
                db.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (otp_row['id'],))
            
            # Clear OTP from session
            session.pop('signup_otp', None)
            session.pop('signup_otp_expires_at', None)

            # Create the user account now

            pending = session.get('pending_user')

            if not pending:

                db.close()

                flash('Session data lost. Please sign up again.', 'error')

                return redirect(url_for('signup'))

            db.execute(

                "INSERT INTO users (id, full_name, email, password_hash) VALUES (?, ?, ?, ?)",

                (generate_user_id(), pending['full_name'], pending['email'], pending['password_hash'])

            )

            db.commit()

            db.close()

            # Clean up session

            session.pop('otp_email', None)

            session.pop('otp_purpose', None)

            session.pop('pending_user', None)

            flash('Email verified! Account created successfully. Please log in.', 'success')

            return redirect(url_for('login'))



        elif purpose == 'admin_login':
            # Check session fallback first for serverless Vercel compatibility
            session_otp = session.get('admin_login_otp')
            session_expiry_str = session.get('admin_login_otp_expires_at')
            verified = False
            
            if session_otp and session_expiry_str:
                try:
                    exp = datetime.fromisoformat(session_expiry_str)
                    if session_otp == entered_otp and datetime.utcnow() <= exp:
                        verified = True
                except Exception:
                    pass
                    
            if not verified:
                otp_row = db.execute(
                    "SELECT * FROM email_verifications WHERE email = ? AND purpose = 'admin_login' AND used = 0 ORDER BY id DESC LIMIT 1",
                    (email,)
                ).fetchone()

                if not otp_row:
                    db.close()
                    flash('No active OTP found. Please log in again.', 'error')
                    return redirect(url_for('login'))

                try:
                    expires_at = datetime.fromisoformat(otp_row['expires_at'])
                except Exception:
                    expires_at = datetime.utcnow()

                if otp_row['otp'] != entered_otp:
                    db.close()
                    flash('Invalid OTP code. Please check and try again.', 'error')
                    return render_template('verify_otp.html', purpose=purpose, email=email)

                if datetime.utcnow() > expires_at:
                    db.close()
                    flash('This OTP has expired. Please log in again.', 'error')
                    return redirect(url_for('login'))

                # Mark OTP used
                db.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (otp_row['id'],))
            
            # Clear OTP from session
            session.pop('admin_login_otp', None)
            session.pop('admin_login_otp_expires_at', None)

            

            pending = session.get('pending_admin_user')

            if not pending:

                db.close()

                flash('Session data lost. Please log in again.', 'error')

                return redirect(url_for('login'))

            

            # Log the admin in
            session.permanent = True
            session['user_id'] = pending['id']
            session['user_name'] = pending['full_name']
            session['is_admin'] = True

            

            # Send login alert email

            queue_login_alert_email(pending['email'], pending['full_name'])

            

            db.commit()

            db.close()

            

            # Clean up session

            session.pop('otp_email', None)

            session.pop('otp_purpose', None)

            session.pop('pending_admin_user', None)

            

            flash(f'Welcome back, {pending["full_name"]}!', 'success')

            return redirect(pending.get('next') or url_for('home'))



        else:  # reset flow
            # Check session fallback first for serverless Vercel compatibility
            session_otp = session.get('reset_otp')
            session_expiry_str = session.get('reset_otp_expires_at')
            verified = False
            
            if session_otp and session_expiry_str:
                try:
                    exp = datetime.fromisoformat(session_expiry_str)
                    if session_otp == entered_otp and datetime.utcnow() <= exp:
                        verified = True
                except Exception:
                    pass
                    
            if not verified:
                reset_row = db.execute(
                    "SELECT * FROM password_resets WHERE email = ? AND used = 0 ORDER BY id DESC LIMIT 1",
                    (email,)
                ).fetchone()

                if not reset_row:
                    db.close()
                    flash('No active OTP found. Please request a new one.', 'error')
                    return redirect(url_for('forgot_password'))

                try:
                    expires_at = datetime.fromisoformat(reset_row['expires_at'])
                except Exception:
                    expires_at = datetime.utcnow()

                if reset_row['otp'] != entered_otp:
                    db.close()
                    flash('Invalid OTP code. Please check and try again.', 'error')
                    return render_template('verify_otp.html', purpose=purpose, email=email)

                if datetime.utcnow() > expires_at:
                    db.close()
                    flash('This OTP has expired. Please request a new one.', 'error')
                    return redirect(url_for('forgot_password'))

                db.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (reset_row['id'],))
                db.commit()
            
            db.close()
            
            # Clear OTP from session
            session.pop('reset_otp', None)
            session.pop('reset_otp_expires_at', None)

            session['otp_verified'] = True
            flash('OTP verified successfully. Please choose a new password.', 'success')
            return redirect(url_for('reset_password'))



    return render_template('verify_otp.html', purpose=purpose, email=email)





@app.route('/reset-password', methods=['GET', 'POST'])

def reset_password():

    if 'user_id' in session:

        return redirect(url_for('home'))



    email = session.get('reset_email')

    otp_verified = session.get('otp_verified')



    if not email or not otp_verified:

        flash('Unauthorized access. Please start the password reset flow.', 'error')

        return redirect(url_for('forgot_password'))



    if request.method == 'POST':

        password = request.form.get('password', '')

        confirm_password = request.form.get('confirm_password', '')



        if not password or not confirm_password:

            flash('Please enter and confirm your new password.', 'error')

            return render_template('reset_password.html')



        if len(password) < 6:

            flash('Password must be at least 6 characters.', 'error')

            return render_template('reset_password.html')



        if password != confirm_password:

            flash('Passwords do not match.', 'error')

            return render_template('reset_password.html')



        db = get_db()

        db.execute(

            "UPDATE users SET password_hash = ? WHERE email = ?",

            (hash_password(password), email)

        )

        db.commit()

        db.close()



        session.pop('reset_email', None)

        session.pop('otp_verified', None)

        session.pop('otp_email', None)

        session.pop('otp_purpose', None)



        flash('Your password has been reset successfully! Please log in with your new password.', 'success')

        return redirect(url_for('login'))



    return render_template('reset_password.html')





@app.route('/resend-otp', methods=['POST'])

def resend_otp():

    """Resend OTP for both signup and reset flows."""

    if 'user_id' in session:

        return redirect(url_for('home'))



    email = session.get('otp_email') or session.get('reset_email')

    purpose = session.get('otp_purpose', 'reset')



    if not email:

        flash('Session expired. Please start again.', 'error')

        if purpose == 'signup':

            return redirect(url_for('signup'))

        elif purpose == 'admin_login':

            return redirect(url_for('login'))

        else:

            return redirect(url_for('forgot_password'))



    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()



    db = get_db()

    if purpose == 'signup':
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'signup', ?)",
            (email, otp, expires_at)
        )
        session['signup_otp'] = otp
        session['signup_otp_expires_at'] = expires_at
    elif purpose == 'admin_login':
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'admin_login', ?)",
            (email, otp, expires_at)
        )
        session['admin_login_otp'] = otp
        session['admin_login_otp_expires_at'] = expires_at
    else:
        db.execute(
            "INSERT INTO password_resets (email, otp, expires_at) VALUES (?, ?, ?)",
            (email, otp, expires_at)
        )
        session['reset_otp'] = otp
        session['reset_otp_expires_at'] = expires_at

    db.commit()

    db.close()



    if not queue_otp_email(email, otp, purpose=purpose):

        flash('Failed to resend OTP. Please check SMTP configuration.', 'error')

    else:

        flash('A new OTP has been sent to your email address.', 'success')



    return redirect(url_for('verify_otp'))





# ─────── Google OAuth 2.0 ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/login/google')

def google_login():

    client_id = os.environ.get('GOOGLE_CLIENT_ID')

    if not client_id:

        # Render the gorgeous Mock Google Consent Page for testing

        return render_template('mock_google_consent.html')

        

    # Actual Google Auth flow

    # Generate state for CSRF protection

    state = secrets.token_hex(16)

    session['oauth_state'] = state

    

    # Determine redirect URI dynamically

    redirect_uri = url_for('google_callback', _external=True)

    

    params = {

        'client_id': client_id,

        'redirect_uri': redirect_uri,

        'response_type': 'code',

        'scope': 'openid email profile',

        'state': state,

        'prompt': 'select_account'

    }

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    return redirect(auth_url)





@app.route('/login/google/callback')

def google_callback():

    client_id = os.environ.get('GOOGLE_CLIENT_ID')

    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    

    # If not configured, this might be a mock callback trigger

    if not client_id or not client_secret:

        # Check if we have mock query params

        mock_email = request.args.get('mock_email')

        mock_name = request.args.get('mock_name')

        if mock_email and mock_name:

            return handle_google_user_login(mock_email, mock_name)

        flash("Google Authentication environment variables are not configured.", "error")

        return redirect(url_for('login'))

        

    code = request.args.get('code')

    state = request.args.get('state')

    

    # Verify state against CSRF

    stored_state = session.pop('oauth_state', None)

    if not state or state != stored_state:

        flash("Authentication failed: CSRF state mismatch.", "error")

        return redirect(url_for('login'))

        

    if not code:

        flash("Authentication failed: No authorization code received.", "error")

        return redirect(url_for('login'))

        

    # Exchange authorization code for access token

    redirect_uri = url_for('google_callback', _external=True)

    

    try:

        token_url = "https://oauth2.googleapis.com/token"

        data = {

            'code': code,

            'client_id': client_id,

            'client_secret': client_secret,

            'redirect_uri': redirect_uri,

            'grant_type': 'authorization_code'

        }

        r = requests.post(token_url, data=data, timeout=10)

        token_data = r.json()

        

        if 'error' in token_data:

            flash(f"Failed to retrieve access token: {token_data.get('error_description', token_data['error'])}", "error")

            return redirect(url_for('login'))

            

        access_token = token_data.get('access_token')

        

        # Get user info from Google

        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

        headers = {'Authorization': f'Bearer {access_token}'}

        user_r = requests.get(userinfo_url, headers=headers, timeout=10)

        user_info = user_r.json()

        

        email = user_info.get('email')

        name = user_info.get('name', email.split('@')[0])

        

        if not email:

            flash("Failed to retrieve user email from Google.", "error")

            return redirect(url_for('login'))

            

        return handle_google_user_login(email, name)

        

    except Exception as e:

        flash(f"An error occurred during Google authentication: {str(e)}", "error")

        return redirect(url_for('login'))





def handle_google_user_login(email, name):

    db = get_db()

    # Check if user exists

    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    

    if not user:

        # Create a new user with a random password hash since they sign in via Google

        random_pwd = secrets.token_hex(16)

        db.execute(

            "INSERT INTO users (id, full_name, email, password_hash) VALUES (?, ?, ?, ?)",

            (generate_user_id(), name, email, hash_password(random_pwd))

        )

        db.commit()

        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        

    db.close()
    
    if bool(user['is_admin']):
        # Generate OTP and store in email_verifications
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        
        db = get_db()
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'admin_login', ?)",
            (user['email'], otp, expires_at)
        )
        db.commit()
        db.close()
        
        # Save admin login OTP to session for stateless Vercel compatibility
        session['admin_login_otp'] = otp
        session['admin_login_otp_expires_at'] = expires_at

        session['otp_email'] = user['email']
        session['otp_purpose'] = 'admin_login'
        session['pending_admin_user'] = {
            'id': user['id'],
            'full_name': user['full_name'],
            'email': user['email'],
            'next': url_for('home')
        }
        
        if not queue_otp_email(user['email'], otp, purpose='admin_login'):
            print(f"[ERROR] Failed to send admin login OTP to {user['email']}")
            
        flash('Google authenticated successfully. A 6-digit verification code has been sent to your email. Please verify to log in as administrator.', 'success')
        return redirect(url_for('verify_otp'))
        
    # Log regular user in
    session.permanent = True
    session['user_id'] = user['id']
    session['user_name'] = user['full_name']
    session['is_admin'] = False
    
    # Send login alert email
    queue_login_alert_email(user['email'], user['full_name'])
    
    flash(f"Successfully signed in as {user['full_name']} via Google!", "success")
    return redirect(url_for('home'))





# ─────── Admin Dashboard ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/admin')

def admin_redirect():

    return redirect(url_for('admin_dashboard'))



@app.route('/admin/dashboard')

@admin_required

def admin_dashboard():

    db = get_db()

    

    # Get statistics

    total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    total_enquiries = db.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0]

    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    pending_enquiries = db.execute("SELECT COUNT(*) FROM enquiries WHERE status = 'Pending'").fetchone()[0]

    total_stocks = db.execute("SELECT SUM(stocks) FROM products").fetchone()[0] or 0

    

    # Get lists

    products_raw = db.execute("SELECT * FROM products ORDER BY category, name").fetchall()

    products_list = []

    for p in products_raw:

        p_dict = dict(p)

        imgs = db.execute("SELECT image_filename FROM product_images WHERE product_id = ?", (p['id'],)).fetchall()

        p_dict['images'] = [img['image_filename'] for img in imgs]

        p_dict['images_csv'] = ", ".join(p_dict['images'])

        products_list.append(p_dict)



    enquiries_list = db.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()

    users_list = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()

    

    # Get all orders

    orders_raw = db.execute(

        """

        SELECT o.*, u.full_name as user_name, u.email as user_email 

        FROM orders o

        JOIN users u ON o.user_id = u.id

        ORDER BY o.created_at DESC

        """

    ).fetchall()

    

    orders_list = []

    for order in orders_raw:

        o_dict = dict(order)

        items = db.execute(

            """

            SELECT oi.*, p.name as product_name 

            FROM order_items oi

            JOIN products p ON oi.product_id = p.id

            WHERE oi.order_id = ?

            """,

            (order['id'],)

        ).fetchall()

        o_dict['items'] = [dict(item) for item in items]

        

        orders_list.append(o_dict)

        

    carousel_slides = db.execute("SELECT * FROM carousel_slides ORDER BY slide_order ASC").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
    subcategories = db.execute("SELECT s.*, c.display_name as parent_category_name FROM subcategories s JOIN categories c ON s.category_name = c.name ORDER BY s.category_name, s.display_order").fetchall()
    promo_codes = db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
    shipping_rates = db.execute("SELECT * FROM location_shipping_charges ORDER BY CASE WHEN UPPER(state) = 'DEFAULT' THEN 1 ELSE 0 END, state ASC").fetchall()

    db.close()

    return render_template(
        'admin_dashboard.html',
        total_products=total_products,
        total_enquiries=total_enquiries,
        total_users=total_users,
        pending_enquiries=pending_enquiries,
        total_stocks=total_stocks,
        products=products_list,
        enquiries=enquiries_list,
        users=users_list,
        orders=orders_list,
        carousel_slides=carousel_slides,
        categories=categories,
        subcategories=subcategories,
        promo_codes=promo_codes,
        shipping_rates=shipping_rates,
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "")
    )





@app.route('/admin/add-product', methods=['POST'])

@admin_required

def admin_add_product():

    name = request.form.get('name', '').strip()

    category = request.form.get('category', '').strip()

    sub_category = request.form.get('sub_category', '').strip()

    description = request.form.get('description', '').strip()

    price = float(request.form.get('price', 0.0) or 0.0)

    stocks = int(request.form.get('stocks', 0) or 0)

    unit = request.form.get('unit', '100g').strip()

    is_bestseller = 1 if request.form.get('is_bestseller') else 0
    discount_percent = float(request.form.get('discount_percent', 0.0) or 0.0)
    shipping_charge = float(request.form.get('shipping_charge', 0.0) or 0.0)
    gst_rate = float(request.form.get('gst_rate', 0.0) or 0.0)

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Gather images from all sources (local uploads take priority)
    image_list = []

    # 1. Local uploads FIRST (highest priority)
    uploaded_files = request.files.getlist('local_images')
    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            file.save(filepath)
            image_list.append(filename)

    # 2. Remote/manual inputs only if no local file was uploaded
    if not image_list:
        remote_images = request.form.get('remote_images', '').strip()
        manual_images = request.form.get('images', '').strip()
        combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
        if combined_csv:
            image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    primary_image = image_list[0] if image_list else ('Tea.jpg' if category == 'Tea' else 'Turmeric-Powder.jpg')

    from database import generate_product_id
    product_id = generate_product_id()

    db = get_db()
    db.execute(
        "INSERT INTO products (id, name, category, sub_category, description, image_filename, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (product_id, name, category, sub_category, description, primary_image, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate)
    )



    # Insert into product_images mapping table

    if not image_list:

        db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, primary_image))

    else:

        for img in image_list:

            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, img))

            

    db.commit()

    invalidate_cache('all_products_list')

    db.close()



    flash(f'Product "{name}" added successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/edit-product/<id>', methods=['POST'])

@admin_required

def admin_edit_product(id):

    name = request.form.get('name', '').strip()

    category = request.form.get('category', '').strip()

    sub_category = request.form.get('sub_category', '').strip()

    description = request.form.get('description', '').strip()

    price = float(request.form.get('price', 0.0) or 0.0)

    stocks = int(request.form.get('stocks', 0) or 0)

    unit = request.form.get('unit', '100g').strip()

    is_bestseller = 1 if request.form.get('is_bestseller') else 0
    discount_percent = float(request.form.get('discount_percent', 0.0) or 0.0)
    shipping_charge = float(request.form.get('shipping_charge', 0.0) or 0.0)
    gst_rate = float(request.form.get('gst_rate', 0.0) or 0.0)

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Gather images from all sources (local uploads take priority)
    image_list = []

    # 1. Local uploads FIRST (highest priority)
    uploaded_files = request.files.getlist('local_images')
    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            file.save(filepath)
            image_list.append(filename)

    # 2. Remote/manual inputs only if no local file was uploaded
    if not image_list:
        remote_images = request.form.get('remote_images', '').strip()
        manual_images = request.form.get('images', '').strip()
        combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
        if combined_csv:
            image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    primary_image = image_list[0] if image_list else ('Tea.jpg' if category == 'Tea' else 'Turmeric-Powder.jpg')

    db = get_db()
    db.execute(
        "UPDATE products SET name = ?, category = ?, sub_category = ?, description = ?, image_filename = ?, price = ?, stocks = ?, unit = ?, is_bestseller = ?, discount_percent = ?, shipping_charge = ?, gst_rate = ? WHERE id = ?",
        (name, category, sub_category, description, primary_image, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate, id)
    )



    # Update images mapping table

    db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))

    if not image_list:

        db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (id, primary_image))

    else:

        for img in image_list:

            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (id, img))



    db.commit()

    invalidate_cache('all_products_list')

    db.close()



    flash(f'Product "{name}" updated successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/delete-product/<id>', methods=['POST'])

@admin_required

def admin_delete_product(id):

    db = get_db()

    product = db.execute("SELECT name FROM products WHERE id = ?", (id,)).fetchone()

    if product:

        db.execute("DELETE FROM products WHERE id = ?", (id,))

        db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))

        db.commit()
        invalidate_cache('all_products_list')
        flash(f'Product "{product["name"]}" deleted successfully.', 'success')

    else:

        flash('Product not found.', 'error')

    db.close()

    return redirect(url_for('admin_dashboard'))



@app.route('/admin/bulk-delete-products', methods=['POST'])
@admin_required
def admin_bulk_delete_products():
    product_ids = request.form.getlist('product_ids')
    if not product_ids:
        flash('No products selected for deletion.', 'error')
        return redirect(url_for('admin_dashboard') + '#products-tab')

    db = get_db()
    deleted_count = 0
    try:
        for pid in product_ids:
            product = db.execute("SELECT name FROM products WHERE id = ?", (pid,)).fetchone()
            if product:
                db.execute("DELETE FROM products WHERE id = ?", (pid,))
                db.execute("DELETE FROM product_images WHERE product_id = ?", (pid,))
                deleted_count += 1
        db.commit()
        invalidate_cache('all_products_list')
        if deleted_count > 0:
            flash(f'Successfully deleted {deleted_count} selected products.', 'success')
        else:
            flash('No products found or deleted.', 'error')
    except Exception as e:
        print(f"[BULK DELETE] Error: {e}")
        flash('An error occurred during bulk deletion.', 'error')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard') + '#products-tab')






# ─────── Promo Code Administration ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────



@app.route('/admin/add-promo', methods=['POST'])

@admin_required

def admin_add_promo():

    code = request.form.get('code', '').strip().upper()

    discount_type = request.form.get('discount_type', 'percent').strip()

    discount_value = float(request.form.get('discount_value', 0) or 0)

    min_order_amount = float(request.form.get('min_order_amount', 0) or 0)

    max_uses = int(request.form.get('max_uses', 0) or 0)

    expires_at = request.form.get('expires_at', '').strip() or None



    if not code:

        flash("Promo code cannot be empty.", "error")

        return redirect(url_for('admin_dashboard'))

    if discount_value <= 0:

        flash("Discount value must be greater than 0.", "error")

        return redirect(url_for('admin_dashboard'))

    if discount_type == 'percent' and discount_value > 100:

        flash("Percent discount cannot exceed 100%.", "error")

        return redirect(url_for('admin_dashboard'))



    db = get_db()

    try:

        db.execute(

            """INSERT INTO promo_codes

               (code, discount_type, discount_value, min_order_amount, max_uses, expires_at)

               VALUES (?, ?, ?, ?, ?, ?)""",

            (code, discount_type, discount_value, min_order_amount, max_uses, expires_at)

        )

        db.commit()

        flash(f"Promo code '{code}' created successfully.", "success")

    except Exception as e:

        flash(f"Error creating promo code: {str(e)}", "error")

    finally:

        db.close()

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/toggle-promo/<int:id>', methods=['POST'])

@admin_required

def admin_toggle_promo(id):

    db = get_db()

    promo = db.execute("SELECT * FROM promo_codes WHERE id = ?", (id,)).fetchone()

    if promo:

        new_state = 0 if promo['is_active'] else 1

        db.execute("UPDATE promo_codes SET is_active = ? WHERE id = ?", (new_state, id))

        db.commit()

        state_label = "activated" if new_state else "deactivated"

        flash(f"Promo '{promo['code']}' {state_label}.", "success")

    else:

        flash("Promo code not found.", "error")

    db.close()

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/delete-promo/<int:id>', methods=['POST'])

@admin_required

def admin_delete_promo(id):

    db = get_db()

    promo = db.execute("SELECT * FROM promo_codes WHERE id = ?", (id,)).fetchone()

    if promo:

        db.execute("DELETE FROM promo_codes WHERE id = ?", (id,))

        db.commit()

        flash(f"Promo code '{promo['code']}' deleted.", "success")

    else:

        flash("Promo code not found.", "error")

    db.close()

    return redirect(url_for('admin_dashboard'))







@app.route('/admin/delete-enquiry/<int:id>', methods=['POST'])

@admin_required

def admin_delete_enquiry(id):

    db = get_db()

    db.execute("DELETE FROM enquiries WHERE id = ?", (id,))

    db.commit()

    db.close()

    flash('Enquiry deleted successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/enquiry/update-status/<int:id>/<string:status>', methods=['POST'])

@admin_required

def admin_update_enquiry_status(id, status):

    if status not in ['Pending', 'Accepted', 'Declined']:

        flash("Invalid status update requested.", "error")

        return redirect(url_for('admin_dashboard'))

    db = get_db()

    db.execute("UPDATE enquiries SET status = ? WHERE id = ?", (status, id))

    db.commit()

    db.close()

    flash(f"Proposal status updated to '{status}'.", "success")

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/resolve-enquiry/<int:id>', methods=['POST'])

@admin_required

def admin_resolve_enquiry(id):

    db = get_db()

    enquiry = db.execute("SELECT status FROM enquiries WHERE id = ?", (id,)).fetchone()

    if enquiry:

        new_status = 'Resolved' if enquiry['status'] == 'Pending' else 'Pending'

        db.execute("UPDATE enquiries SET status = ? WHERE id = ?", (new_status, id))

        db.commit()

        flash(f'Enquiry status updated to {new_status}.', 'success')

    else:

        flash('Enquiry not found.', 'error')

    db.close()

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/update-order-status/<int:id>', methods=['POST'])

@admin_required

def admin_update_order_status(id):

    if request.is_json:

        status = request.json.get('status', '').strip()

    else:

        status = request.form.get('status', '').strip()



    if status not in ['Processing', 'Shipped', 'Delivered', 'Cancelled']:

        if request.is_json:

            return jsonify({'success': False, 'error': 'Invalid status'}), 400

        flash("Invalid order status.", "error")

        return redirect(url_for('admin_dashboard'))

        

    db = get_db()

    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, id))

    db.commit()

    db.close()

    

    # Send status email notification

    try:

        queue_order_status_update_email(id, status, host_url=request.host_url)

    except Exception as mail_err:

        print(f"[MAIL ALERT ERROR] Failed to send status update email: {str(mail_err)}")

        

    if request.is_json:

        return jsonify({'success': True, 'status': status})



    # Fetch order_number for a friendlier flash message

    db2 = get_db()

    o = db2.execute("SELECT order_number FROM orders WHERE id = ?", (id,)).fetchone()

    db2.close()

    label = o['order_number'] if o and o['order_number'] else f'#{id}'

    flash(f"Order {label} status updated to {status}.", "success")

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/orders/<int:id>')

@admin_required

def admin_order_detail(id):

    db = get_db()

    order = db.execute(

        """

        SELECT o.*,

               u.full_name  AS user_name,

               u.email      AS user_email

        FROM orders o

        JOIN users u ON o.user_id = u.id

        WHERE o.id = ?

        """,

        (id,)

    ).fetchone()



    if not order:

        db.close()

        flash(f"Order #{id} not found.", "error")

        return redirect(url_for('admin_dashboard'))



    items = db.execute(

        """

        SELECT oi.*,

               p.name           AS product_name,

               p.unit           AS unit,

               COALESCE(

                   (SELECT pi.image_filename FROM product_images pi

                    WHERE pi.product_id = p.id LIMIT 1),

                   p.image_filename

               ) AS image_filename

        FROM order_items oi

        JOIN products p ON oi.product_id = p.id

        WHERE oi.order_id = ?

        """,

        (id,)

    ).fetchall()

    db.close()

    return render_template('admin_order_detail.html', order=order, items=items)





@app.route('/admin/orders/<int:id>/invoice')

@admin_required

def admin_invoice(id):

    db = get_db()

    order = db.execute(

        """

        SELECT o.*,

               u.full_name AS user_name,

               u.email     AS user_email

        FROM orders o

        JOIN users u ON o.user_id = u.id

        WHERE o.id = ?

        """,

        (id,)

    ).fetchone()

    if not order:

        db.close()

        flash(f"Order #{id} not found.", "error")

        return redirect(url_for('admin_dashboard'))



    items = db.execute(

        """

        SELECT oi.*,

               p.name AS product_name,

               p.unit AS unit,

               p.gst_rate AS gst_rate

        FROM order_items oi

        JOIN products p ON oi.product_id = p.id

        WHERE oi.order_id = ?

        """,

        (id,)

    ).fetchall()

    db.close()

    return render_template(

        'invoice.html',

        order=order,

        items=items,

        back_url=url_for('admin_order_detail', id=id),

        back_label='Back to Order Detail',

        viewer='admin'

    )





@app.route('/orders/<int:id>/invoice')

def customer_invoice(id):

    if 'user_id' not in session:

        flash('Please log in to view your invoice.', 'error')

        return redirect(url_for('login'))



    db = get_db()

    order = db.execute(

        """

        SELECT o.*,

               u.full_name AS user_name,

               u.email     AS user_email

        FROM orders o

        JOIN users u ON o.user_id = u.id

        WHERE o.id = ? AND o.user_id = ?

        """,

        (id, session['user_id'])

    ).fetchone()

    if not order:

        db.close()

        flash("Invoice not found or you don't have permission to view it.", "error")

        return redirect(url_for('my_orders'))



    items = db.execute(

        """

        SELECT oi.*,

               p.name AS product_name,

               p.unit AS unit,

               p.gst_rate AS gst_rate

        FROM order_items oi

        JOIN products p ON oi.product_id = p.id

        WHERE oi.order_id = ?

        """,

        (id,)

    ).fetchall()

    db.close()

    return render_template(

        'invoice.html',

        order=order,

        items=items,

        back_url=url_for('my_orders'),

        back_label='Back to My Orders',

        viewer='customer'

    )

















# ─────── Carousel Slides Administration ───────



@app.route('/admin/add-slide', methods=['POST'])

@admin_required

def admin_add_slide():

    badge_text = request.form.get('badge_text', '').strip()

    badge_icon = request.form.get('badge_icon', 'leaf').strip()

    title = request.form.get('title', '').strip()

    description = request.form.get('description', '').strip()

    button_text = request.form.get('button_text', 'Explore Products').strip()

    button_link = request.form.get('button_link', '/products').strip()

    slide_order = int(request.form.get('slide_order', 0) or 0)



    if not title:

        flash('Slide title is required.', 'error')

        return redirect(url_for('admin_dashboard'))



    # Image handling: local upload takes strict priority over remote url
    uploaded_file = request.files.get('local_images')
    remote_image = request.form.get('remote_images', '').strip()
    image_filename = ''

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):
        filename = secure_filename(uploaded_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        base, extension = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{extension}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            counter += 1
        uploaded_file.save(filepath)
        image_filename = filename
    elif remote_image:
        image_filename = remote_image
    else:
        image_filename = 'hero_tea_garden.png'



    db = get_db()

    db.execute(

        "INSERT INTO carousel_slides (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",

        (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order)

    )

    db.commit()

    db.close()

    

    flash('Carousel slide added successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/edit-slide/<int:id>', methods=['POST'])

@admin_required

def admin_edit_slide(id):

    badge_text = request.form.get('badge_text', '').strip()

    badge_icon = request.form.get('badge_icon', 'leaf').strip()

    title = request.form.get('title', '').strip()

    description = request.form.get('description', '').strip()

    button_text = request.form.get('button_text', 'Explore Products').strip()

    button_link = request.form.get('button_link', '/products').strip()

    slide_order = int(request.form.get('slide_order', 0) or 0)



    if not title:

        flash('Slide title is required.', 'error')

        return redirect(url_for('admin_dashboard'))



    db = get_db()

    slide = db.execute("SELECT image_filename FROM carousel_slides WHERE id = ?", (id,)).fetchone()

    if not slide:

        db.close()

        flash('Slide not found.', 'error')

        return redirect(url_for('admin_dashboard'))



    image_filename = slide['image_filename']

    uploaded_file = request.files.get('local_images')

    remote_image = request.form.get('remote_images', '').strip()

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):

        filename = secure_filename(uploaded_file.filename)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        base, extension = os.path.splitext(filename)

        counter = 1

        while os.path.exists(filepath):

            filename = f"{base}_{counter}{extension}"

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            counter += 1

        uploaded_file.save(filepath)

        image_filename = filename

    elif remote_image:

        image_filename = remote_image



    db.execute(

        """

        UPDATE carousel_slides 

        SET image_filename = ?, badge_icon = ?, badge_text = ?, title = ?, description = ?, button_text = ?, button_link = ?, slide_order = ?

        WHERE id = ?

        """,

        (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order, id)

    )

    db.commit()

    db.close()



    flash('Carousel slide updated successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/delete-slide/<int:id>', methods=['POST'])

@admin_required

def admin_delete_slide(id):

    db = get_db()

    db.execute("DELETE FROM carousel_slides WHERE id = ?", (id,))

    db.commit()

    db.close()

    flash('Carousel slide deleted successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





# ─────── Categories Administration ───────



@app.route('/admin/add-category', methods=['POST'])

@admin_required

def admin_add_category():

    import sqlite3
    print("[ADD CATEGORY] request.form:", request.form)
    print("[ADD CATEGORY] request.files:", request.files)

    name = request.form.get('name', '').strip()

    display_name = request.form.get('display_name', '').strip()

    description = request.form.get('description', '').strip()

    display_order = int(request.form.get('display_order', 0) or 0)



    if not name or not display_name:

        flash('Category name and display name are required.', 'error')

        return redirect(url_for('admin_dashboard'))



    # Image handling (local upload takes precedence over remote url)

    uploaded_file = request.files.get('local_images')

    remote_image = request.form.get('remote_images', '').strip()

    image_filename = 'Tea.jpg'

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):

        filename = secure_filename(uploaded_file.filename)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        base, extension = os.path.splitext(filename)

        counter = 1

        while os.path.exists(filepath):

            filename = f"{base}_{counter}{extension}"

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            counter += 1

        uploaded_file.save(filepath)

        image_filename = filename

    elif remote_image:

        image_filename = remote_image



    db = get_db()

    try:

        db.execute(

            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",

            (name, display_name, description, image_filename, display_order)

        )

        db.commit()
        invalidate_cache('nav_categories', 'nav_categories_list')
        flash(f'Category "{display_name}" added successfully.', 'success')

    except sqlite3.IntegrityError:

        flash(f'Category name "{name}" already exists.', 'error')

    db.close()

    

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/edit-category/<int:id>', methods=['POST'])

@admin_required

def admin_edit_category(id):

    print("[EDIT CATEGORY] request.form:", request.form)
    print("[EDIT CATEGORY] request.files:", request.files)

    name = request.form.get('name', '').strip()

    display_name = request.form.get('display_name', '').strip()

    description = request.form.get('description', '').strip()

    display_order = int(request.form.get('display_order', 0) or 0)



    if not name or not display_name:

        flash('Category name and display name are required.', 'error')

        return redirect(url_for('admin_dashboard'))



    db = get_db()

    category = db.execute("SELECT image_filename FROM categories WHERE id = ?", (id,)).fetchone()

    if not category:

        db.close()

        flash('Category not found.', 'error')

        return redirect(url_for('admin_dashboard'))



    image_filename = category['image_filename']

    uploaded_file = request.files.get('local_images')

    remote_image = request.form.get('remote_images', '').strip()

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):

        filename = secure_filename(uploaded_file.filename)

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        base, extension = os.path.splitext(filename)

        counter = 1

        while os.path.exists(filepath):

            filename = f"{base}_{counter}{extension}"

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            counter += 1

        uploaded_file.save(filepath)

        image_filename = filename

    elif remote_image:

        image_filename = remote_image



    db.execute(

        """

        UPDATE categories 

        SET name = ?, display_name = ?, description = ?, image_filename = ?, display_order = ?

        WHERE id = ?

        """,

        (name, display_name, description, image_filename, display_order, id)

    )

    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()



    flash(f'Category "{display_name}" updated successfully.', 'success')

    return redirect(url_for('admin_dashboard'))





@app.route('/admin/delete-category/<int:id>', methods=['POST'])

@admin_required

def admin_delete_category(id):

    db = get_db()

    db.execute("DELETE FROM categories WHERE id = ?", (id,))

    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()

    flash('Category deleted successfully.', 'success')

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/add-subcategory', methods=['POST'])
@admin_required
def admin_add_subcategory():
    category_name = request.form.get('category_name', '').strip()
    name = request.form.get('name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    description = request.form.get('description', '').strip()
    display_order = int(request.form.get('display_order', 0) or 0)

    if not category_name or not name or not display_name:
        flash('Parent category, subcategory name, and display name are required.', 'error')
        return redirect(url_for('admin_dashboard') + '#categories-tab')

    db = get_db()
    try:
        db.execute(
            "INSERT INTO subcategories (category_name, name, display_name, description, display_order) VALUES (?, ?, ?, ?, ?)",
            (category_name, name, display_name, description, display_order)
        )
        db.commit()
        invalidate_cache('nav_categories', 'nav_categories_list')
        flash(f'Subcategory "{display_name}" added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Subcategory name "{name}" already exists.', 'error')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard') + '#categories-tab')


@app.route('/admin/delete-subcategory/<int:id>', methods=['POST'])
@admin_required
def admin_delete_subcategory(id):
    db = get_db()
    db.execute("DELETE FROM subcategories WHERE id = ?", (id,))
    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()
    flash('Subcategory deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#categories-tab')





# Global context processor to inject categories dynamically

@app.context_processor

def inject_global_data():

    try:

        db = get_db()

        categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()

        subcategories = db.execute("SELECT * FROM subcategories ORDER BY category_name, display_order ASC").fetchall()

        db.close()

        return {'global_categories': categories, 'global_subcategories': subcategories}

    except Exception:

        return {'global_categories': [], 'global_subcategories': []}





@app.route('/api/resolve-onedrive', methods=['POST'])

@admin_required

def api_resolve_onedrive():

    url = request.json.get('url', '').strip()

    if not url:

        return jsonify({'error': 'No URL provided'}), 400

    

    try:

        import requests

        # If it's a short URL (1drv.ms), resolve the redirect first

        if "1drv.ms" in url:

            response = requests.get(url, allow_redirects=True, timeout=10)

            final_url = response.url

        else:

            final_url = url

            

        # Convert redir link to embed link

        if "onedrive.live.com/redir" in final_url:

            final_url = final_url.replace("onedrive.live.com/redir", "onedrive.live.com/embed")

        elif "onedrive.live.com/redir.aspx" in final_url:

            final_url = final_url.replace("onedrive.live.com/redir.aspx", "onedrive.live.com/embed.aspx")

            

        return jsonify({'success': True, 'resolved_url': final_url})

    except Exception as e:

        return jsonify({'error': f'Failed to resolve URL: {str(e)}'}), 500





@app.route('/api/admin/orders', methods=['GET'])

@admin_required

def api_admin_orders():

    db = get_db()

    orders_raw = db.execute(

        """

        SELECT o.*, u.full_name as user_name, u.email as user_email 

        FROM orders o

        JOIN users u ON o.user_id = u.id

        ORDER BY o.created_at DESC

        """

    ).fetchall()

    

    orders_list = []

    for order in orders_raw:

        o_dict = dict(order)

        items = db.execute(

            """

            SELECT oi.*, p.name as product_name 

            FROM order_items oi

            JOIN products p ON oi.product_id = p.id

            WHERE oi.order_id = ?

            """,

            (order['id'],)

        ).fetchall()

        o_dict['items'] = [dict(item) for item in items]

        orders_list.append(o_dict)

    db.close()

    return jsonify(orders_list)





if __name__ == '__main__':

    app.run(debug=True, port=5000)

