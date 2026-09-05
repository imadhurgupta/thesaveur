from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db
from services.auth_service import hash_password

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile', endpoint='profile')
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


@profile_bp.route('/profile/update-info', methods=['POST'], endpoint='profile_update_info')
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


@profile_bp.route('/profile/change-password', methods=['POST'], endpoint='profile_change_password')
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
