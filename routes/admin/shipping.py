import sqlite3
from flask import Blueprint, request, redirect, url_for, flash
from database import get_db
from services.auth_service import admin_required

admin_shipping_bp = Blueprint('admin_shipping_bp', __name__)


@admin_shipping_bp.route('/admin/shipping/add', methods=['POST'], endpoint='admin_add_shipping')
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


@admin_shipping_bp.route('/admin/shipping/edit/<int:id>', methods=['POST'], endpoint='admin_edit_shipping')
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


@admin_shipping_bp.route('/admin/shipping/delete/<int:id>', methods=['POST'], endpoint='admin_delete_shipping')
@admin_required
def admin_delete_shipping(id):
    db = get_db()
    db.execute("DELETE FROM location_shipping_charges WHERE id = ?", (id,))
    db.commit()
    db.close()
    flash('Shipping rate deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#shipping-tab')
