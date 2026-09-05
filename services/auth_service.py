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
    """Generate a unique alphanumeric order number, e.g. AMT-A3X9KZ2Q."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f'AMT-{suffix}'


def allowed_file(filename):
    """Validate image file extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_video_file(filename):
    """Validate video file extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS
