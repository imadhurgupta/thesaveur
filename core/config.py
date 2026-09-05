import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# App Secrets & Session
SECRET_KEY = os.environ.get('SECRET_KEY', 'am_trader_dev_secret_key_2024')
SESSION_COOKIE_NAME = 'thesaveur_session'

# Razorpay Configuration
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '').strip()
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '').strip()
IS_REAL_MODE = True

# PayPal Configuration
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', '').strip()
PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET', '').strip()
PAYPAL_MODE = os.environ.get('PAYPAL_MODE', 'sandbox').strip().lower()
PAYPAL_EXCHANGE_RATE = float(os.environ.get('PAYPAL_EXCHANGE_RATE_INR_TO_USD', 1.0) or 1.0)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# File Upload Settings
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Admin Credentials
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@thesaveur.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
