from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from database import get_db, init_db, generate_user_id
import hashlib
import random
import string
from datetime import datetime, timedelta
from functools import wraps
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from werkzeug.utils import secure_filename
import urllib.parse
import secrets
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'am_trader_dev_secret_key_2024')

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


def generate_order_number():
    """Generate a unique alphanumeric order number, e.g. AMT-A3X9KZ2Q."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f'AMT-{suffix}'


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


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
    else:
        subject = "Password Reset OTP – The Saveur"
        heading = "Password Reset Request"
        body_text = ("We received a request to reset your password. Use the verification code below "
                     "to proceed with the password reset process. This OTP is valid for 10 minutes.")
        
    try:
        port = int(smtp_port)
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_sender
        msg['To'] = receiver_email
        
        # HTML body with premium styling matching brand colors
        html_body = f"""
        <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
                <div style="background: linear-gradient(135deg, #2D5016 0%, #5a9e35 100%); padding: 30px; text-align: center; color: #ffffff;">
                    <span style="font-size: 40px;">ðŸƒ</span>
                    <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
                </div>
                <div style="padding: 40px 30px; line-height: 1.6;">
                    <h2 style="color: #2D5016; margin-top: 0; font-size: 20px;">{heading}</h2>
                    <p style="color: #3d3d3d; font-size: 15px;">Hello,</p>
                    <p style="color: #3d3d3d; font-size: 15px;">{body_text}</p>
                    
                    <div style="background-color: #FAF7F2; border: 1px dashed #C8860A; border-radius: 8px; padding: 20px; text-align: center; margin: 30px 0;">
                        <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #C8860A; font-family: monospace;">{otp}</span>
                    </div>
                    
                    <p style="color: #3d3d3d; font-size: 15px;">If you did not request this, please ignore this email or contact support if you have concerns.</p>
                </div>
                <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                    <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html_body, 'html')
        msg.attach(part)
        
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
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_sender
        msg['To'] = receiver_email
        
        part = MIMEText(html_body, 'html')
        msg.attach(part)
        
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
    html_body = f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2D5016 0%, #5a9e35 100%); padding: 30px; text-align: center; color: #ffffff;">
                <span style="font-size: 40px;">ðŸƒ</span>
                <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: #2D5016; margin-top: 0; font-size: 20px;">Security Alert: New Login</h2>
                <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
                <p style="color: #3d3d3d; font-size: 15px;">Your account logged in successfully at <strong>{time_str}</strong>.</p>
                <p style="color: #3d3d3d; font-size: 15px;">If this was you, no action is required. If you did not log in, please reset your password immediately or contact support.</p>
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """
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
        
    html_body = f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2D5016 0%, #5a9e35 100%); padding: 30px; text-align: center; color: #ffffff;">
                <span style="font-size: 40px;">ðŸƒ</span>
                <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: #2D5016; margin-top: 0; font-size: 20px;">Thank You for Your Order!</h2>
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
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_custom_html_email(user_email, subject, html_body)


def send_order_shipped_email(user_email, user_name, order_number, tracking_url):
    """Notify user of order shipment with tracking link."""
    subject = f"Your Order #{order_number} is Shipped! ðŸšš | The Saveur"
    html_body = f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2D5016 0%, #5a9e35 100%); padding: 30px; text-align: center; color: #ffffff;">
                <span style="font-size: 40px;">ðŸšš</span>
                <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: #2D5016; margin-top: 0; font-size: 20px;">Your Order has Shipped!</h2>
                <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
                <p style="color: #3d3d3d; font-size: 15px;">Good news! Your order #{order_number} is on the way. Our delivery partner is delivering it to you.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{tracking_url}" style="background-color: #C8860A; color: white; padding: 14px 28px; text-decoration: none; border-radius: 99px; font-weight: bold; font-size: 15px; box-shadow: 0 4px 12px rgba(200,134,10,0.3); display: inline-block;">
                        ðŸ“ Live Tracking Link
                    </a>
                </div>
                
                <p style="color: #6b6b6b; font-size: 13px; text-align: center;">Click the button above to track your delivery partner and see live updates.</p>
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_custom_html_email(user_email, subject, html_body)


def send_order_delivered_email(user_email, user_name, order_number):
    """Notify user of successful delivery."""
    subject = f"Your Order #{order_number} is Delivered! 🎉 | The Saveur"
    html_body = f"""
    <html>
    <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
            <div style="background: linear-gradient(135deg, #2D5016 0%, #5a9e35 100%); padding: 30px; text-align: center; color: #ffffff;">
                <span style="font-size: 40px;">ðŸŽ</span>
                <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
            </div>
            <div style="padding: 40px 30px; line-height: 1.6;">
                <h2 style="color: #2D5016; margin-top: 0; font-size: 20px;">Order Delivered!</h2>
                <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
                <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been successfully delivered. We hope you love your premium teas and spices!</p>
                <p style="color: #3d3d3d; font-size: 15px;">Thank you for shopping with The Saveur.</p>
            </div>
            <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
            </div>
        </div>
    </body>
    </html>
    """
    send_custom_html_email(user_email, subject, html_body)


def send_order_status_update_email(order_id, new_status):
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
        tracking_url = f"{request.host_url}track-order/{order_id}"
        send_order_shipped_email(user_email, user_name, order_number, tracking_url)
    elif new_status == 'Delivered':
        send_order_delivered_email(user_email, user_name, order_number)
    elif new_status == 'Cancelled':
        subject = f"Your Order #{order_number} has been Cancelled – The Saveur"
        html_body = f"""
        <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #FAF7F2; padding: 40px; margin: 0; color: #1A1A1A;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.05); overflow: hidden;">
                <div style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 30px; text-align: center; color: #ffffff;">
                    <span style="font-size: 40px;">❌</span>
                    <h1 style="margin: 10px 0 0; font-family: 'Playfair Display', serif; font-size: 24px; font-weight: bold;">The Saveur</h1>
                </div>
                <div style="padding: 40px 30px; line-height: 1.6;">
                    <h2 style="color: #c0392b; margin-top: 0; font-size: 20px;">Order Cancelled</h2>
                    <p style="color: #3d3d3d; font-size: 15px;">Hello {user_name},</p>
                    <p style="color: #3d3d3d; font-size: 15px;">Your order #{order_number} has been cancelled. If you paid online, the refund will be initiated to your source account.</p>
                    <p style="color: #3d3d3d; font-size: 15px;">If you have any questions, please contact our support team.</p>
                </div>
                <div style="background-color: #FAF7F2; padding: 20px; text-align: center; font-size: 12px; color: #6b6b6b; border-top: 1px solid rgba(0,0,0,0.05);">
                    <p style="margin: 0;">&copy; 2026 The Saveur. Sourced from the finest farms.</p>
                </div>
            </div>
        </body>
        </html>
        """
        send_custom_html_email(user_email, subject, html_body)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Access denied. Administrator privileges required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function




# ─────── Home ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    db = get_db()
    bestsellers = db.execute(
        "SELECT * FROM products WHERE is_bestseller = 1 LIMIT 6"
    ).fetchall()
    carousel_slides = db.execute(
        "SELECT * FROM carousel_slides ORDER BY slide_order ASC"
    ).fetchall()
    categories = db.execute(
        "SELECT * FROM categories ORDER BY display_order ASC"
    ).fetchall()
    db.close()
    return render_template('index.html', bestsellers=bestsellers, carousel_slides=carousel_slides, categories=categories)


# ─────── Products ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

@app.route('/products')
def products():
    category = request.args.get('category', 'all').strip()
    db = get_db()
    
    # Query categories to match case-insensitively
    categories = db.execute("SELECT name, display_name FROM categories").fetchall()
    
    matched_category_name = None
    for cat in categories:
        if cat['name'].lower() == category.lower():
            matched_category_name = cat['name']
            break
            
    if matched_category_name:
        products_list = db.execute(
            "SELECT * FROM products WHERE category = ? ORDER BY name",
            (matched_category_name,)
        ).fetchall()
    else:
        # Default to all products if 'all' or unmatched
        products_list = db.execute(
            "SELECT * FROM products ORDER BY category, name"
        ).fetchall()
        category = 'all'
        
    db.close()
    return render_template('products.html', products=products_list, active_filter=category)


@app.route('/product/<int:id>')
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
        
    db.close()
    return render_template('product_detail.html', product=product, images=image_list)


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


# ─────── Shopping Cart ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

@app.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0.0
    
    db = get_db()
    for prod_id, qty in cart.items():
        product = db.execute("SELECT * FROM products WHERE id = ?", (int(prod_id),)).fetchone()
        if product:
            p_dict = dict(product)
            p_dict['quantity'] = qty
            p_dict['item_total'] = product['price'] * qty
            subtotal += p_dict['item_total']
            cart_items.append(p_dict)
    db.close()
    
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
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
    
    flash(f"Added {qty} {product['name']} to cart.", "success")
    return redirect(url_for('view_cart'))


@app.route('/cart/update/<int:product_id>', methods=['POST'])
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


@app.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    flash("Item removed from cart.", "success")
    return redirect(url_for('view_cart'))


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

    db.close()
    
    return render_template('profile.html', user=user)


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
        product = db.execute("SELECT * FROM products WHERE id = ?", (int(prod_id),)).fetchone()
        if product:
            p_dict = dict(product)
            p_dict['quantity'] = qty
            p_dict['item_total'] = product['price'] * qty
            subtotal += p_dict['item_total']
            cart_items.append(p_dict)
    # Fetch user info for address pre-filling
    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    db.close()
    
    return render_template('checkout.html', cart_items=cart_items, subtotal=subtotal, user=user)


@app.route('/checkout/submit', methods=['POST'])
def checkout_submit():
    if 'user_id' not in session:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for('login'))
        
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for('products'))
        
    shipping_address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    zip_code = request.form.get('zip', '').strip()
    payment_method = request.form.get('payment_method', 'UPI').strip()
    promo_code_input = request.form.get('promo_code', '').strip().upper()
    discount_amount_input = float(request.form.get('discount_amount', 0) or 0)

    if not shipping_address or not city or not state or not zip_code:
        flash("Please fill in all shipping details.", "error")
        return redirect(url_for('checkout'))

    db = get_db()
    try:
        # Check stock and calculate total amount
        total_amount = 0.0
        order_items_to_create = []
        for prod_id, qty in cart.items():
            product = db.execute("SELECT * FROM products WHERE id = ?", (int(prod_id),)).fetchone()
            if not product:
                flash(f"One of the products in your cart is no longer available.", "error")
                return redirect(url_for('view_cart'))

            if product['stocks'] < qty:
                flash(f"Insufficient stock for {product['name']}. Only {product['stocks']} available.", "error")
                return redirect(url_for('view_cart'))

            total_amount += product['price'] * qty
            order_items_to_create.append({
                'product_id': product['id'],
                'product_name': product['name'],
                'quantity': qty,
                'price': product['price']
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

        final_total = round(total_amount - final_discount, 2)

        # Create order record
        order_number = generate_order_number()
        cursor = db.execute(
            """INSERT INTO orders
               (user_id, total_amount, shipping_address, city, state, zip_code,
                payment_method, status, discount_amount, promo_code, order_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'Processing', ?, ?, ?)""",
            (session['user_id'], final_total, shipping_address, city, state, zip_code,
             payment_method, final_discount, applied_promo['code'] if applied_promo else '',
             order_number)
        )
        order_id = cursor.lastrowid

        # Create order items and update stock
        for item in order_items_to_create:
            db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                (order_id, item['product_id'], item['quantity'], item['price'])
            )
            db.execute(
                "UPDATE products SET stocks = stocks - ? WHERE id = ?",
                (item['quantity'], item['product_id'])
            )

        # Increment promo usage
        if applied_promo:
            db.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?",
                (applied_promo['id'],)
            )

        db.commit()
        
        # Send Order Confirmation / Invoice Email
        try:
            user = db.execute("SELECT email, full_name FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if user:
                send_order_confirmation_email(
                    user['email'], 
                    user['full_name'], 
                    order_number, 
                    final_total, 
                    f"{shipping_address}, {city}, {state} – {zip_code}", 
                    order_items_to_create
                )
        except Exception as mail_err:
            print(f"[MAIL ALERT ERROR] Failed to send order confirmation email: {str(mail_err)}")

        session['cart'] = {}
        session.modified = True

        if applied_promo:
            flash(f"Order {order_number} placed! Promo '{applied_promo['code']}' saved you ₹{final_discount:.2f}. 🎉", "success")
        else:
            flash(f"Order {order_number} placed successfully!", "success")
        return redirect(url_for('my_orders'))
    except Exception as e:
        db.rollback()
        flash(f"An error occurred while placing the order: {str(e)}", "error")
        return redirect(url_for('checkout'))
    finally:
        db.close()


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

        # Store pending user data in session (not created yet)
        session['otp_email'] = email
        session['otp_purpose'] = 'signup'
        session['pending_user'] = {
            'full_name': full_name,
            'email': email,
            'password_hash': hash_password(password)
        }

        if not send_otp_email(email, otp, purpose='signup'):
            flash('Failed to send OTP email. Please check SMTP configuration and try again.', 'error')
            return render_template('signup.html')

        flash('A 6-digit verification code has been sent to your email. Please verify to complete registration.', 'success')
        return redirect(url_for('verify_otp'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND password_hash = ?",
            (email, hash_password(password))
        ).fetchone()
        db.close()

        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['is_admin'] = bool(user['is_admin'])

            
            # Send login alert email
            send_login_alert_email(user['email'], user['full_name'])
            
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
            return render_template('login.html')

    return render_template('login.html')


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

        session['otp_email'] = email
        session['otp_purpose'] = 'reset'
        session['reset_email'] = email  # keep for backward compat with reset_password route

        if not send_otp_email(email, otp, purpose='reset'):
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

        else:  # reset flow
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
        return redirect(url_for('signup') if purpose == 'signup' else url_for('forgot_password'))

    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

    db = get_db()
    if purpose == 'signup':
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'signup', ?)",
            (email, otp, expires_at)
        )
    else:
        db.execute(
            "INSERT INTO password_resets (email, otp, expires_at) VALUES (?, ?, ?)",
            (email, otp, expires_at)
        )
    db.commit()
    db.close()

    if not send_otp_email(email, otp, purpose=purpose):
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
    
    # Log the user in
    session['user_id'] = user['id']
    session['user_name'] = user['full_name']
    session['is_admin'] = bool(user['is_admin'])
    
    # Send login alert email
    send_login_alert_email(user['email'], user['full_name'])
    
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
    promo_codes = db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()

    
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
        promo_codes=promo_codes,
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "")
    )


@app.route('/admin/add-product', methods=['POST'])
@admin_required
def admin_add_product():
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    price = float(request.form.get('price', 0.0) or 0.0)
    stocks = int(request.form.get('stocks', 0) or 0)
    unit = request.form.get('unit', '100g').strip()
    is_bestseller = 1 if request.form.get('is_bestseller') else 0

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Gather images from all sources (local uploads, Google Drive/OneDrive urls, manual CSV)
    image_list = []
    
    # 1. Remote and manual inputs
    remote_images = request.form.get('remote_images', '').strip()
    manual_images = request.form.get('images', '').strip()
    combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
    
    if combined_csv:
        image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    # 2. Local uploads
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

    primary_image = image_list[0] if image_list else ('Tea.jpg' if category == 'Tea' else 'Turmeric-Powder.jpg')

    db = get_db()
    cursor = db.execute(
        "INSERT INTO products (name, category, description, image_filename, price, stocks, unit, is_bestseller) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, category, description, primary_image, price, stocks, unit, is_bestseller)
    )
    product_id = cursor.lastrowid

    # Insert into product_images mapping table
    if not image_list:
        db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, primary_image))
    else:
        for img in image_list:
            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, img))
            
    db.commit()
    db.close()

    flash(f'Product "{name}" added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit-product/<int:id>', methods=['POST'])
@admin_required
def admin_edit_product(id):
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()
    price = float(request.form.get('price', 0.0) or 0.0)
    stocks = int(request.form.get('stocks', 0) or 0)
    unit = request.form.get('unit', '100g').strip()
    is_bestseller = 1 if request.form.get('is_bestseller') else 0

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Gather images from all sources
    image_list = []
    
    # 1. Remote and manual inputs
    remote_images = request.form.get('remote_images', '').strip()
    manual_images = request.form.get('images', '').strip()
    combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
    
    if combined_csv:
        image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    # 2. Local uploads
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

    primary_image = image_list[0] if image_list else ('Tea.jpg' if category == 'Tea' else 'Turmeric-Powder.jpg')

    db = get_db()
    db.execute(
        "UPDATE products SET name = ?, category = ?, description = ?, image_filename = ?, price = ?, stocks = ?, unit = ?, is_bestseller = ? WHERE id = ?",
        (name, category, description, primary_image, price, stocks, unit, is_bestseller, id)
    )

    # Update images mapping table
    db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
    if not image_list:
        db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (id, primary_image))
    else:
        for img in image_list:
            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (id, img))

    db.commit()
    db.close()

    flash(f'Product "{name}" updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-product/<int:id>', methods=['POST'])
@admin_required
def admin_delete_product(id):
    db = get_db()
    product = db.execute("SELECT name FROM products WHERE id = ?", (id,)).fetchone()
    if product:
        db.execute("DELETE FROM products WHERE id = ?", (id,))
        db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
        db.commit()
        flash(f'Product "{product["name"]}" deleted successfully.', 'success')
    else:
        flash('Product not found.', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))


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
        send_order_status_update_email(id, status)
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
               p.unit AS unit
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
               p.unit AS unit
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

    # Image handling (local upload or remote url)
    image_filename = 'hero_tea_garden.png'
    remote_image = request.form.get('remote_images', '').strip()
    
    if remote_image:
        image_filename = remote_image
    else:
        uploaded_file = request.files.get('local_images')
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
    remote_image = request.form.get('remote_images', '').strip()
    
    if remote_image:
        image_filename = remote_image
    else:
        uploaded_file = request.files.get('local_images')
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
    name = request.form.get('name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    description = request.form.get('description', '').strip()
    display_order = int(request.form.get('display_order', 0) or 0)

    if not name or not display_name:
        flash('Category name and display name are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    # Image handling (local upload or remote url)
    image_filename = 'Tea.jpg'
    remote_image = request.form.get('remote_images', '').strip()
    
    if remote_image:
        image_filename = remote_image
    else:
        uploaded_file = request.files.get('local_images')
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

    db = get_db()
    try:
        db.execute(
            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
            (name, display_name, description, image_filename, display_order)
        )
        db.commit()
        flash(f'Category "{display_name}" added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Category name "{name}" already exists.', 'error')
    db.close()
    
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/edit-category/<int:id>', methods=['POST'])
@admin_required
def admin_edit_category(id):
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
    remote_image = request.form.get('remote_images', '').strip()
    
    if remote_image:
        image_filename = remote_image
    else:
        uploaded_file = request.files.get('local_images')
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

    db.execute(
        """
        UPDATE categories 
        SET name = ?, display_name = ?, description = ?, image_filename = ?, display_order = ?
        WHERE id = ?
        """,
        (name, display_name, description, image_filename, display_order, id)
    )
    db.commit()
    db.close()

    flash(f'Category "{display_name}" updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete-category/<int:id>', methods=['POST'])
@admin_required
def admin_delete_category(id):
    db = get_db()
    db.execute("DELETE FROM categories WHERE id = ?", (id,))
    db.commit()
    db.close()
    flash('Category deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


# Global context processor to inject categories dynamically
@app.context_processor
def inject_global_data():
    try:
        db = get_db()
        categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        db.close()
        return {'global_categories': categories}
    except Exception:
        return {'global_categories': []}


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
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, port=5000)
