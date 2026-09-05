from flask import Blueprint, request, redirect, url_for, flash
from database import get_db
from services.auth_service import admin_required

admin_promos_bp = Blueprint('admin_promos_bp', __name__)


@admin_promos_bp.route('/admin/add-promo', methods=['POST'], endpoint='admin_add_promo')
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


@admin_promos_bp.route('/admin/toggle-promo/<int:id>', methods=['POST'], endpoint='admin_toggle_promo')
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


@admin_promos_bp.route('/admin/delete-promo/<int:id>', methods=['POST'], endpoint='admin_delete_promo')
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
