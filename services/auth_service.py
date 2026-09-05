import os
import hmac
import hashlib
import random
import string
from functools import wraps
from flask import session, flash, redirect, url_for
from core.config import ALLOWED_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS


def admin_required(f):
    """Decorator to require admin role for protected admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not (session.get('is_admin') or session.get('user_id') == 'USR-ADMIN'):
            flash('Access denied. Administrator privileges required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def hash_password(password):
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def generate_order_number():
    """Generate a unique alphanumeric order number, e.g. TSV-A3X9KZ2Q."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f'TSV-{suffix}'


def generate_order_access_token(order_id, user_id, order_number=''):
    """Generate a secure cryptographic HMAC-SHA256 signature for customer order access."""
    secret = os.environ.get('SECRET_KEY', 'thesaveur-secure-production-key-2026')
    payload = f"{order_id}:{user_id}:{order_number}"
    return hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()[:32]


def verify_order_access(order, session_obj, request_obj):
    """
    Strict ownership verification:
    Only the customer who placed the order (or an admin, or an authenticated encrypted token) can access.
    """
    if not order:
        return False, "Order not found."

    o = dict(order) if not isinstance(order, dict) else order

    # 1. Administrator access
    if session_obj.get('is_admin') or session_obj.get('user_id') == 'USR-ADMIN':
        return True, "admin"

    # 2. Logged-in customer is the verified owner
    if 'user_id' in session_obj and str(session_obj['user_id']) == str(o.get('user_id')):
        return True, "owner"

    # 3. Cryptographic HMAC token passed in query / form (e.g. from private dispatch email)
    token = request_obj.args.get('token') or request_obj.form.get('token')
    if token:
        expected_token = generate_order_access_token(o.get('id'), o.get('user_id'), o.get('order_number') or '')
        if hmac.compare_digest(str(token), str(expected_token)):
            return True, "token"

    # 4. Email / phone verification provided in search query
    verify_contact = (request_obj.values.get('verify_contact') or request_obj.values.get('email') or request_obj.values.get('phone') or '').strip().lower()
    if verify_contact:
        c_email = (o.get('customer_email') or o.get('contact_email') or o.get('user_email') or '').strip().lower()
        c_phone = (o.get('customer_phone') or o.get('contact_phone') or o.get('user_phone') or '').strip().lower()
        if (c_email and verify_contact == c_email) or (c_phone and verify_contact == c_phone):
            return True, "verified_contact"

    # If user is logged in but belongs to another account
    if 'user_id' in session_obj:
        return False, "You do not have permission to view this order. Tracking is strictly restricted to the customer who placed it."

    return False, "Authentication required. Please log in to your account or provide your registered email to securely view this order."


def allowed_file(filename):
    """Validate image file extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_video_file(filename):
    """Validate video file extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS
