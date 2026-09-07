import os
import shutil
import sqlite3
import datetime
from flask import Blueprint, request, redirect, url_for, flash, jsonify, send_file, g
from database import get_db, DB_PATH
from services.auth_service import admin_required
from services.cache_service import invalidate_cache
from services.email_service import send_order_status_update_email

admin_system_bp = Blueprint('admin_system_bp', __name__)


# ── Courier API Keys & System Settings ────────────────────────────────────────

SETTING_KEYS = [
    'DELHIVERY_API_TOKEN',
    'SHIPROCKET_EMAIL',
    'SHIPROCKET_PASSWORD',
    'TRACK17_API_KEY',
    'TRACKINGMORE_API_KEY',
    'SHIPGLOBAL_EMAIL',
    'SHIPGLOBAL_PASSWORD',
    'SHIPGLOBAL_DEFAULT_SERVICE',
    'SHIPGLOBAL_SANDBOX_MODE',
    'SHIPGLOBAL_API_TOKEN',
    'TRACKING_WEBHOOK_SECRET',
    'AUTO_TRACKING_ENABLED',
    'TRACKING_POLL_INTERVAL_MINUTES',
]


@admin_system_bp.route('/admin/settings/tracking', methods=['POST'], endpoint='admin_save_tracking_settings')
@admin_required
def admin_save_tracking_settings():
    """Save courier API keys and tracking configuration to system_settings."""
    from services.tracking_service import save_system_setting, get_system_setting
    data = request.get_json(silent=True) or request.form
    saved = []

    # If submitting from standard HTML form and checkbox was unchecked
    if not request.is_json and 'SHIPGLOBAL_EMAIL' in data:
        sandbox_val = '1' if data.get('SHIPGLOBAL_SANDBOX_MODE') in ('1', 'on', 'true', True) else '0'
        save_system_setting('SHIPGLOBAL_SANDBOX_MODE', sandbox_val)
        saved.append('SHIPGLOBAL_SANDBOX_MODE')

    for key in SETTING_KEYS:
        if key == 'SHIPGLOBAL_SANDBOX_MODE' and not request.is_json:
            continue
        if key not in data:
            continue
        val = str(data.get(key) or '').strip()
        # For password / token fields, skip empty value (keep existing)
        if not val and key in ('SHIPROCKET_PASSWORD', 'DELHIVERY_API_TOKEN', 'TRACK17_API_KEY', 'TRACKINGMORE_API_KEY', 'SHIPGLOBAL_PASSWORD', 'SHIPGLOBAL_API_TOKEN', 'TRACKING_WEBHOOK_SECRET'):
            continue
        save_system_setting(key, val)
        saved.append(key)
    
    if request.is_json:
        return jsonify({'success': True, 'message': f"Saved {len(saved)} setting(s) successfully.", 'saved': saved})

    flash(f"Tracking settings saved ({len(saved)} keys updated).", "success")
    return redirect(url_for('admin_dashboard') + '#settings-tab')


@admin_system_bp.route('/admin/settings/tracking', methods=['GET'], endpoint='admin_get_tracking_settings')
@admin_required
def admin_get_tracking_settings():
    """Return current tracking settings as JSON (secrets masked)."""
    from services.tracking_service import get_all_settings
    settings = get_all_settings()
    # Mask secret values
    for secret_key in ('SHIPROCKET_PASSWORD', 'DELHIVERY_API_TOKEN', 'TRACK17_API_KEY', 'TRACKINGMORE_API_KEY', 'SHIPGLOBAL_PASSWORD', 'SHIPGLOBAL_API_TOKEN', 'TRACKING_WEBHOOK_SECRET'):
        if settings.get(secret_key):
            settings[secret_key] = '••••••••'
    return jsonify(settings)


@admin_system_bp.route('/admin/settings/shipglobal/test-auth', methods=['POST'], endpoint='admin_test_shipglobal_auth')
@admin_required
def admin_test_shipglobal_auth():
    """Test connection to ShipGlobal API or validate Sandbox mode."""
    from services.tracking_service import get_shipglobal_auth_token, get_system_setting
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')
    token = data.get('token') or data.get('api_token')
    sandbox = data.get('sandbox')

    # If Sandbox mode is specifically requested or enabled in settings
    is_sandbox = sandbox is True or str(sandbox).lower() in ('1', 'true', 'on')
    if is_sandbox or (sandbox is None and get_system_setting('SHIPGLOBAL_SANDBOX_MODE', '0') == '1'):
        return jsonify({
            'success': True,
            'sandbox': True,
            'message': 'ShipGlobal Sandbox Mode is active! You can generate real 4x6 thermal test labels and waybills immediately.'
        })

    token, err = get_shipglobal_auth_token(email=email, password=password, token=token)
    if token:
        return jsonify({'success': True, 'message': 'Successfully authenticated with ShipGlobal API!'})

    # Return friendly diagnostic message with sandbox suggestion if 401
    return jsonify({
        'success': False,
        'error': err or 'Failed to authenticate with ShipGlobal',
        'can_sandbox': True
    })


@admin_system_bp.route('/admin/orders/<order_ref>/refresh-tracking', methods=['POST'],
                       endpoint='admin_refresh_order_tracking')
@admin_required
def admin_refresh_order_tracking(order_ref):
    """Manually trigger an immediate tracking fetch for a specific order."""
    from services.tracking_service import update_order_from_tracking, get_tracking_events

    db = get_db()
    order = db.execute(
        "SELECT id, tracking_number FROM orders WHERE order_number = ? OR CAST(id AS TEXT) = ?",
        (order_ref, order_ref)
    ).fetchone()
    db.close()

    if not order:
        return jsonify({'success': False, 'error': 'Order not found'}), 404
    if not order['tracking_number']:
        return jsonify({'success': False, 'error': 'No tracking number on this order'}), 400

    result = update_order_from_tracking(order['id'], host_url=request.host_url)
    events = get_tracking_events(order['id'])
    result['events_list'] = events
    return jsonify(result)


@admin_system_bp.route('/admin/orders/<order_ref>/add-checkpoint', methods=['POST'],
                       endpoint='admin_add_tracking_checkpoint')
@admin_required
def admin_add_tracking_checkpoint(order_ref):
    """
    Manually add a live tracking scan event for ANY delivery partner.
    Advances order status, commits to database, and notifies customer.
    """
    from services.tracking_service import add_manual_tracking_checkpoint, get_tracking_events

    db = get_db()
    order = db.execute(
        "SELECT id, courier_partner, tracking_number FROM orders WHERE order_number = ? OR CAST(id AS TEXT) = ?",
        (order_ref, order_ref)
    ).fetchone()
    db.close()

    if not order:
        return jsonify({'success': False, 'error': 'Order not found'}), 404

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    status_raw = data.get('status', '').strip()
    location   = data.get('location', '').strip()
    message    = data.get('message', '').strip()
    courier    = data.get('courier_partner', '').strip() or order['courier_partner'] or 'Express Courier'

    if not status_raw:
        return jsonify({'success': False, 'error': 'Status is required'}), 400

    res = add_manual_tracking_checkpoint(
        order_id=order['id'],
        courier=courier,
        status_raw=status_raw,
        location=location,
        message=message,
        host_url=request.host_url
    )
    res['events_list'] = get_tracking_events(order['id'])
    return jsonify(res)





@admin_system_bp.route('/api/admin/orders', methods=['GET'], endpoint='api_admin_orders')
@admin_required
def api_admin_orders():
    db = get_db()
    orders_raw = db.execute(
        """
        SELECT o.*, u.full_name as user_name, u.email as user_email 
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.status != 'Pending Payment'
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


@admin_system_bp.route('/admin/backup-db', endpoint='admin_backup_db')
@admin_required
def admin_backup_db():
    if not os.path.exists(DB_PATH):
        flash("Database file not found.", "error")
        return redirect(url_for('admin_dashboard'))
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"thesaveur_backup_{timestamp}.db"
    return send_file(DB_PATH, as_attachment=True, download_name=backup_filename)


@admin_system_bp.route('/admin/restore-db', methods=['POST'], endpoint='admin_restore_db')
@admin_required
def admin_restore_db():
    if 'backup_file' not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for('admin_dashboard') + '#settings-tab')
        
    file = request.files['backup_file']
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for('admin_dashboard') + '#settings-tab')
        
    if not file.filename.endswith('.db'):
        flash("Invalid file format. Please upload a valid .db SQLite file.", "error")
        return redirect(url_for('admin_dashboard') + '#settings-tab')

    temp_restore_path = DB_PATH + ".restore_temp"
    try:
        file.save(temp_restore_path)
        
        with open(temp_restore_path, "rb") as f:
            header = f.read(16)
            if not header.startswith(b"SQLite format 3\x00"):
                os.remove(temp_restore_path)
                flash("Validation failed: The file is not a valid SQLite database.", "error")
                return redirect(url_for('admin_dashboard') + '#settings-tab')
                
        test_conn = sqlite3.connect(temp_restore_path)
        test_cursor = test_conn.cursor()
        test_cursor.execute("PRAGMA integrity_check")
        res = test_cursor.fetchone()
        test_conn.close()
        
        if not res or res[0] != "ok":
            os.remove(temp_restore_path)
            flash("Integrity check failed: SQLite database file is corrupted.", "error")
            return redirect(url_for('admin_dashboard') + '#settings-tab')
            
    except Exception as e:
        if os.path.exists(temp_restore_path):
            os.remove(temp_restore_path)
        flash(f"Error during validation: {str(e)}", "error")
        return redirect(url_for('admin_dashboard') + '#settings-tab')

    try:
        if hasattr(g, 'sqlite_db'):
            g.sqlite_db.close()
            delattr(g, 'sqlite_db')
    except Exception:
        pass

    backup_of_current = DB_PATH + ".pre_restore_bak"
    try:
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_of_current)
            
        shutil.move(temp_restore_path, DB_PATH)
        
        invalidate_cache('all_products_list', 'nav_categories', 'nav_categories_list')
        
        flash("Database restored successfully! All products, categories, orders, and users have been updated.", "success")
        
        if os.path.exists(backup_of_current):
            os.remove(backup_of_current)
            
    except Exception as swap_err:
        if os.path.exists(backup_of_current):
            shutil.move(backup_of_current, DB_PATH)
        if os.path.exists(temp_restore_path):
            os.remove(temp_restore_path)
        flash(f"Restore failed during installation: {str(swap_err)}", "error")
        
    return redirect(url_for('admin_dashboard') + '#settings-tab')
