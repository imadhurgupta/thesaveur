import os
import random
import secrets
import urllib.parse
from datetime import datetime, timedelta
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db, generate_user_id
from services.auth_service import hash_password
from services.email_service import queue_otp_email, queue_login_alert_email
from core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/signup', methods=['GET', 'POST'], endpoint='signup')
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


@auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')
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

                queue_login_alert_email(user['email'], user['full_name'])
                flash(f'Welcome back, {user["full_name"]}!', 'success')
                return redirect(next_url if next_url else url_for('home'))
        else:
            flash('Invalid email or password. Please try again.', 'error')
            return render_template('login.html', next=next_url)

    return render_template('login.html', next=next_url)


@auth_bp.route('/logout', endpoint='logout')
def logout():
    user_name = session.get('user_name', 'User')
    session.clear()
    flash(f'Goodbye, {user_name}! You have been logged out.', 'success')
    return redirect(url_for('home'))


@auth_bp.route('/login/google', endpoint='google_login')
def google_login():
    if not GOOGLE_CLIENT_ID:
        return render_template('mock_google_consent.html')

    state = secrets.token_hex(16)
    session['oauth_state'] = state
    redirect_uri = url_for('google_callback', _external=True)

    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account'
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


@auth_bp.route('/login/google/callback', endpoint='google_callback')
def google_callback():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        mock_email = request.args.get('mock_email')
        mock_name = request.args.get('mock_name')
        if mock_email and mock_name:
            return handle_google_user_login(mock_email, mock_name)
        flash("Google Authentication environment variables are not configured.", "error")
        return redirect(url_for('login'))

    code = request.args.get('code')
    state = request.args.get('state')

    stored_state = session.pop('oauth_state', None)
    if not state or state != stored_state:
        flash("Authentication failed: CSRF state mismatch.", "error")
        return redirect(url_for('login'))

    if not code:
        flash("Authentication failed: No authorization code received.", "error")
        return redirect(url_for('login'))

    redirect_uri = url_for('google_callback', _external=True)

    try:
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        r = requests.post(token_url, data=data, timeout=10)
        token_data = r.json()

        if 'error' in token_data:
            flash(f"Failed to retrieve access token: {token_data.get('error_description', token_data['error'])}", "error")
            return redirect(url_for('login'))

        access_token = token_data.get('access_token')
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        user_r = requests.get(userinfo_url, headers=headers, timeout=10)
        user_info = user_r.json()

        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else 'User')

        if not email:
            flash("Failed to retrieve user email from Google.", "error")
            return redirect(url_for('login'))

        return handle_google_user_login(email, name)
    except Exception as e:
        flash(f"An error occurred during Google authentication: {str(e)}", "error")
        return redirect(url_for('login'))


def handle_google_user_login(email, name):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user:
        random_pwd = secrets.token_hex(16)
        db.execute(
            "INSERT INTO users (id, full_name, email, password_hash) VALUES (?, ?, ?, ?)",
            (generate_user_id(), name, email, hash_password(random_pwd))
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    db.close()

    if bool(user['is_admin']):
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        db = get_db()
        db.execute(
            "INSERT INTO email_verifications (email, otp, purpose, expires_at) VALUES (?, ?, 'admin_login', ?)",
            (user['email'], otp, expires_at)
        )
        db.commit()
        db.close()

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

    session.permanent = True
    session['user_id'] = user['id']
    session['user_name'] = user['full_name']
    session['is_admin'] = False

    queue_login_alert_email(user['email'], user['full_name'])
    flash(f"Successfully signed in as {user['full_name']} via Google!", "success")
    return redirect(url_for('home'))
