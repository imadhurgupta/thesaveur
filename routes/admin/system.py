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
