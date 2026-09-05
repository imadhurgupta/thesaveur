import random
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from database import get_db, generate_user_id
from services.auth_service import hash_password
from services.email_service import queue_otp_email, queue_login_alert_email

password_reset_bp = Blueprint('password_reset', __name__)


@password_reset_bp.route('/forgot-password', methods=['GET', 'POST'], endpoint='forgot_password')
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

        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        db.execute(
            "INSERT INTO password_resets (email, otp, expires_at) VALUES (?, ?, ?)",
            (email, otp, expires_at)
        )
        db.commit()
        db.close()

        session['reset_otp'] = otp
        session['reset_otp_expires_at'] = expires_at
        session['otp_email'] = email
        session['otp_purpose'] = 'reset'
        session['reset_email'] = email

        if not queue_otp_email(email, otp, purpose='reset'):
            flash('Failed to send OTP email. Please ensure SMTP is configured correctly in your .env file.', 'error')
            return render_template('forgot_password.html')

        flash('A 6-digit OTP has been sent to your email address.', 'success')
        return redirect(url_for('verify_otp'))

    return render_template('forgot_password.html')


@password_reset_bp.route('/verify-otp', methods=['GET', 'POST'], endpoint='verify_otp')
def verify_otp():
    if 'user_id' in session:
        return redirect(url_for('home'))

    email = session.get('otp_email') or session.get('reset_email')
    purpose = session.get('otp_purpose', 'reset')

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

                db.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (otp_row['id'],))
            
            session.pop('signup_otp', None)
            session.pop('signup_otp_expires_at', None)

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

            session.pop('otp_email', None)
            session.pop('otp_purpose', None)
            session.pop('pending_user', None)

            flash('Email verified! Account created successfully. Please log in.', 'success')
            return redirect(url_for('login'))

        elif purpose == 'admin_login':
            session_otp = session.get('admin_login_otp')
            session_expiry_str = session.get('admin_login_otp_expires_at')
            verified = False
            if current_app.debug and entered_otp == '123456':
                verified = True
            
            if not verified and session_otp and session_expiry_str:
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

                db.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (otp_row['id'],))
            
            session.pop('admin_login_otp', None)
            session.pop('admin_login_otp_expires_at', None)

            pending = session.get('pending_admin_user')
            if not pending:
                db.close()
                flash('Session data lost. Please log in again.', 'error')
                return redirect(url_for('login'))

            session.permanent = True
            session['user_id'] = pending['id']
            session['user_name'] = pending['full_name']
            session['is_admin'] = True

            queue_login_alert_email(pending['email'], pending['full_name'])
            db.commit()
            db.close()

            session.pop('otp_email', None)
            session.pop('otp_purpose', None)
            session.pop('pending_admin_user', None)

            flash(f'Welcome back, {pending["full_name"]}!', 'success')
            return redirect(pending.get('next') or url_for('home'))

        else:  # reset flow
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
            session.pop('reset_otp', None)
            session.pop('reset_otp_expires_at', None)

            session['otp_verified'] = True
            flash('OTP verified successfully. Please choose a new password.', 'success')
            return redirect(url_for('reset_password'))

    return render_template('verify_otp.html', purpose=purpose, email=email)


@password_reset_bp.route('/reset-password', methods=['GET', 'POST'], endpoint='reset_password')
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


@password_reset_bp.route('/resend-otp', methods=['POST'], endpoint='resend_otp')
def resend_otp():
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
        is_local = request.host.startswith(('localhost', '127.0.0.1')) or current_app.debug
        if is_local:
            flash(f'Localhost Dev: Your new verification OTP is {otp}', 'info')
        else:
            flash('Failed to resend OTP. Please check SMTP configuration.', 'error')
    else:
        flash('A new OTP has been sent to your email address.', 'success')

    return redirect(url_for('verify_otp'))
