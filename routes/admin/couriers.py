import random
import re
from flask import Blueprint, request, jsonify
from database import get_db
from services.auth_service import admin_required

admin_couriers_bp = Blueprint('admin_couriers_bp', __name__)


@admin_couriers_bp.route('/api/admin/couriers/list', methods=['GET'], endpoint='api_admin_list_couriers')
@admin_required
def api_admin_list_couriers():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM custom_couriers ORDER BY name ASC").fetchall()
        db.close()
        return jsonify({
            'success': True,
            'couriers': [dict(r) for r in rows]
        })
    except Exception as e:
        db.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_couriers_bp.route('/api/admin/couriers/add', methods=['POST'], endpoint='api_admin_add_courier')
@admin_required
def api_admin_add_courier():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = (data.get('name') or '').strip()
    url_pattern = (data.get('url_pattern') or '').strip()
    sample_format = (data.get('sample_format') or '').strip()
    color = (data.get('color') or '#16a34a').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Courier name is required.'}), 400

    code = re.sub(r'[^a-zA-Z0-9_]', '', name.lower().replace(' ', '_'))
    if not code:
        code = 'custom_' + str(random.randint(1000, 9999))

    db = get_db()
    try:
        existing = db.execute("SELECT * FROM custom_couriers WHERE code = ? OR LOWER(name) = LOWER(?)", (code, name)).fetchone()
        if existing:
            db.execute(
                "UPDATE custom_couriers SET name = ?, url_pattern = ?, sample_format = ?, color = ? WHERE id = ?",
                (name, url_pattern or existing['url_pattern'], sample_format or existing['sample_format'], color, existing['id'])
            )
            db.commit()
            courier_id = existing['id']
            code = existing['code']
        else:
            cur = db.execute(
                "INSERT INTO custom_couriers (name, code, url_pattern, sample_format, color) VALUES (?, ?, ?, ?, ?)",
                (name, code, url_pattern or '{tracking_number}', sample_format or 'Enter tracking number', color)
            )
            db.commit()
            courier_id = cur.lastrowid
        db.close()
        return jsonify({
            'success': True,
            'courier': {
                'id': courier_id,
                'name': name,
                'code': code,
                'url_pattern': url_pattern or '{tracking_number}',
                'sample_format': sample_format or 'Enter tracking number',
                'color': color
            }
        })
    except Exception as e:
        db.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_couriers_bp.route('/api/admin/couriers/update', methods=['POST'], endpoint='api_admin_update_courier')
@admin_required
def api_admin_update_courier():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    courier_id = data.get('id')
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    url_pattern = (data.get('url_pattern') or '').strip()
    sample_format = (data.get('sample_format') or '').strip()
    color = (data.get('color') or '#16a34a').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Courier name cannot be empty.'}), 400

    db = get_db()
    try:
        existing = None
        if courier_id:
            existing = db.execute("SELECT * FROM custom_couriers WHERE id = ?", (courier_id,)).fetchone()
        if not existing and code:
            existing = db.execute("SELECT * FROM custom_couriers WHERE code = ?", (code,)).fetchone()
        if not existing:
            existing = db.execute("SELECT * FROM custom_couriers WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()

        if not existing:
            db.close()
            return jsonify({'success': False, 'error': 'Custom courier not found to update.'}), 404

        target_id = existing['id']
        final_code = existing['code']

        db.execute(
            "UPDATE custom_couriers SET name = ?, url_pattern = ?, sample_format = ?, color = ? WHERE id = ?",
            (name, url_pattern or '{tracking_number}', sample_format or 'Enter tracking number', color, target_id)
        )
        db.commit()
        db.close()

        return jsonify({
            'success': True,
            'message': 'Courier updated successfully.',
            'courier': {
                'id': target_id,
                'name': name,
                'code': final_code,
                'url_pattern': url_pattern or '{tracking_number}',
                'sample_format': sample_format or 'Enter tracking number',
                'color': color
            }
        })
    except Exception as e:
        db.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_couriers_bp.route('/api/admin/couriers/delete/<int:id>', methods=['POST', 'DELETE'], endpoint='api_admin_delete_courier')
@admin_couriers_bp.route('/api/admin/couriers/delete', methods=['POST', 'DELETE'], endpoint='api_admin_delete_courier')
@admin_required
def api_admin_delete_courier(id=None):
    if not id:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        id = data.get('id')
        code = (data.get('code') or '').strip()
    else:
        code = None

    if not id and not code:
        return jsonify({'success': False, 'error': 'Courier ID or code is required for deletion.'}), 400

    db = get_db()
    try:
        if id:
            db.execute("DELETE FROM custom_couriers WHERE id = ?", (id,))
        elif code:
            db.execute("DELETE FROM custom_couriers WHERE code = ?", (code,))
        db.commit()
        db.close()
        return jsonify({'success': True, 'message': 'Courier deleted successfully.'})
    except Exception as e:
        db.close()
        return jsonify({'success': False, 'error': str(e)}), 500
