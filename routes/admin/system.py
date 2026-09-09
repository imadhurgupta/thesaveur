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
    
    import tempfile
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"thesaveur_backup_{timestamp}.db"
    
    temp_dir = tempfile.gettempdir()
    temp_backup_file = os.path.join(temp_dir, backup_filename)
    
    try:
        # Create an atomic, consistent online backup snapshot
        src_conn = sqlite3.connect(DB_PATH)
        dst_conn = sqlite3.connect(temp_backup_file)
        with dst_conn:
            src_conn.backup(dst_conn, pages=0)
        dst_conn.close()
        src_conn.close()
        
        return send_file(
            temp_backup_file,
            as_attachment=True,
            download_name=backup_filename,
            mimetype="application/x-sqlite3"
        )
    except Exception as e:
        print(f"[BACKUP ERROR] {e}")
        return send_file(
            DB_PATH,
            as_attachment=True,
            download_name=backup_filename,
            mimetype="application/x-sqlite3"
        )



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


# ══════════════════════════════════════════════════════════════════════
# SHIPROCKET LOGISTICS & LIVE TRACKING SETTINGS API
# ══════════════════════════════════════════════════════════════════════
@admin_system_bp.route('/api/admin/tracking-settings', methods=['GET'], endpoint='api_admin_get_tracking_settings')
@admin_required
def api_admin_get_tracking_settings():
    """Retrieve current Shiprocket configuration and live connection status."""
    from services.tracking_service import get_system_setting, ShiprocketClient
    client = ShiprocketClient()

    email = get_system_setting('SHIPROCKET_EMAIL') or os.environ.get('SHIPROCKET_EMAIL', '')
    has_password = bool(get_system_setting('SHIPROCKET_PASSWORD') or os.environ.get('SHIPROCKET_PASSWORD', ''))
    auto_enabled = get_system_setting('AUTO_TRACKING_ENABLED', '1') == '1'
    poll_interval = get_system_setting('TRACKING_POLL_INTERVAL_MINUTES', '30')
    webhook_token = get_system_setting('SHIPROCKET_WEBHOOK_TOKEN') or os.environ.get('SHIPROCKET_WEBHOOK_TOKEN', '')
    mock_mode = get_system_setting('SHIPROCKET_MOCK_MODE', '1') == '1'
    last_sync = get_system_setting('SHIPROCKET_LAST_BULK_SYNC', '')

    webhook_url = f"{request.host_url.rstrip('/')}/api/webhooks/delivery/push"

    return jsonify({
        'success': True,
        'email': email,
        'has_password': has_password,
        'auto_tracking_enabled': auto_enabled,
        'poll_interval_minutes': poll_interval,
        'webhook_token': webhook_token,
        'webhook_url': webhook_url,
        'mock_mode': mock_mode,
        'is_configured': client.is_configured(),
        'last_bulk_sync': last_sync
    })


@admin_system_bp.route('/api/admin/tracking-settings', methods=['POST'], endpoint='api_admin_save_tracking_settings')
@admin_required
def api_admin_save_tracking_settings():
    """Save Shiprocket credentials and sync settings into database."""
    from services.tracking_service import set_system_setting, ShiprocketClient

    data = request.get_json(silent=True) or request.form.to_dict() or {}

    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    auto_enabled = '1' if data.get('auto_tracking_enabled') in [True, '1', 'true', 'on'] else '0'
    poll_interval = str(data.get('poll_interval_minutes') or '30').strip()
    webhook_token = (data.get('webhook_token') or '').strip()
    if email:
        set_system_setting('SHIPROCKET_EMAIL', email)
    if password:
        set_system_setting('SHIPROCKET_PASSWORD', password)
        set_system_setting('SHIPROCKET_TOKEN', '')
        set_system_setting('SHIPROCKET_TOKEN_EXPIRES', '')

    set_system_setting('AUTO_TRACKING_ENABLED', auto_enabled)
    set_system_setting('TRACKING_POLL_INTERVAL_MINUTES', poll_interval)
    set_system_setting('SHIPROCKET_WEBHOOK_TOKEN', webhook_token)

    if 'mock_mode' in data:
        mock_mode = '1' if data.get('mock_mode') in [True, '1', 'true', 'on'] else '0'
        set_system_setting('SHIPROCKET_MOCK_MODE', mock_mode)

    return jsonify({
        'success': True,
        'message': 'Shiprocket tracking configuration saved successfully!'
    })


@admin_system_bp.route('/api/admin/tracking-settings/test', methods=['POST'], endpoint='api_admin_test_tracking_connection')
@admin_required
def api_admin_test_tracking_connection():
    """Test authentication against Shiprocket API."""
    from services.tracking_service import ShiprocketClient
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')

    client = ShiprocketClient(email=email, password=password)
    result = client.test_connection()
    return jsonify(result)


@admin_system_bp.route('/api/admin/tracking-settings/sync-all', methods=['POST'], endpoint='api_admin_sync_all_shipments')
@admin_required
def api_admin_sync_all_shipments():
    """Trigger manual bulk sync of all active in-transit shipments."""
    from services.tracking_service import sync_all_active_orders
    summary = sync_all_active_orders(host_url=request.host_url)
    return jsonify({
        'success': True,
        'message': f"Synced {summary.get('total', 0)} active shipments. {summary.get('updated', 0)} updated.",
        'summary': summary
    })


# ══════════════════════════════════════════════════════════════════════
# SHIPGLOBAL LIVE LOGISTICS & LABEL GENERATION SETTINGS API
# ══════════════════════════════════════════════════════════════════════
@admin_system_bp.route('/api/admin/shipglobal-settings', methods=['GET'], endpoint='api_admin_get_shipglobal_settings')
@admin_required
def api_admin_get_shipglobal_settings():
    """Retrieve current ShipGlobal configuration and connection status."""
    from services.shipglobal_service import get_system_setting, ShipGlobalClient, SUPPORTED_SERVICES
    client = ShipGlobalClient()

    email = get_system_setting('SHIPGLOBAL_EMAIL') or os.environ.get('SHIPGLOBAL_EMAIL', '')
    has_password = bool(get_system_setting('SHIPGLOBAL_PASSWORD') or os.environ.get('SHIPGLOBAL_PASSWORD', ''))
    default_service = get_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', 'CIRRO-CLASSIC')
    mock_mode = get_system_setting('SHIPGLOBAL_MOCK_MODE', '0') == '1'
    customer_name = get_system_setting('SHIPGLOBAL_CUSTOMER_NAME', '')

    return jsonify({
        'success': True,
        'email': email,
        'has_password': has_password,
        'default_service': default_service,
        'supported_services': SUPPORTED_SERVICES,
        'mock_mode': mock_mode,
        'customer_name': customer_name,
        'is_configured': client.is_configured()
    })


@admin_system_bp.route('/api/admin/shipglobal-settings', methods=['POST'], endpoint='api_admin_save_shipglobal_settings')
@admin_required
def api_admin_save_shipglobal_settings():
    """Save ShipGlobal credentials and default logistics service into database."""
    from services.shipglobal_service import set_system_setting, ShipGlobalClient

    data = request.get_json(silent=True) or request.form.to_dict() or {}

    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    service = (data.get('default_service') or 'CIRRO-CLASSIC').strip()

    if email:
        set_system_setting('SHIPGLOBAL_EMAIL', email)
    if password:
        set_system_setting('SHIPGLOBAL_PASSWORD', password)
        set_system_setting('SHIPGLOBAL_TOKEN', '')
        set_system_setting('SHIPGLOBAL_TOKEN_EXPIRES', '')

    if service:
        set_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', service)

    if 'mock_mode' in data:
        mock_mode = '1' if data.get('mock_mode') in [True, '1', 'true', 'on'] else '0'
        set_system_setting('SHIPGLOBAL_MOCK_MODE', mock_mode)

    return jsonify({
        'success': True,
        'message': 'ShipGlobal configuration saved successfully!'
    })


@admin_system_bp.route('/api/admin/shipglobal-settings/test', methods=['POST'], endpoint='api_admin_test_shipglobal_connection')
@admin_required
def api_admin_test_shipglobal_connection():
    """Test authentication against live ShipGlobal API (/customers.php)."""
    from services.shipglobal_service import ShipGlobalClient, get_system_setting
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()

    # Fallback to saved credentials if field was left blank
    if not email:
        email = get_system_setting('SHIPGLOBAL_EMAIL')
    if not password:
        password = get_system_setting('SHIPGLOBAL_PASSWORD')

    client = ShipGlobalClient(email=email, password=password)
    result = client.test_connection()
    return jsonify(result)

