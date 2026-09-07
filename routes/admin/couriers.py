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


@admin_couriers_bp.route('/api/admin/couriers/lookup-awb', methods=['GET', 'POST'], endpoint='api_admin_lookup_awb')
@admin_required
def api_admin_lookup_awb():
    """
    Look up complete courier partner information (courier name, code, official tracking URL, EDD)
    from an AWB / Tracking number via courier APIs & patterns.
    """
    data = request.get_json(silent=True) or request.args or request.form.to_dict() or {}
    awb = str(data.get('awb') or data.get('tracking_number') or '').strip()
    if not awb:
        return jsonify({'success': False, 'error': 'AWB number is required.'}), 400

    from services.tracking_service import ShiprocketClient
    from services.couriers_service import COURIER_PARTNERS, get_courier_metadata, generate_tracking_url, normalize_courier_code

    courier_name = None
    courier_code = None
    track_url = None
    edd = None
    origin = None
    destination = None
    current_status = None
    raw_data = {}

    # 1. Query courier tracking API
    try:
        client = ShiprocketClient()
        track_res = client.track_awb(awb)
        if track_res.get('success'):
            courier_name = track_res.get('courier_name')
            track_url = track_res.get('track_url')
            edd = track_res.get('edd')
            origin = track_res.get('origin')
            destination = track_res.get('destination')
            current_status = track_res.get('current_status')
            raw_data = track_res
    except Exception as e:
        print(f"[LOOKUP AWB API ERROR] {e}")

    # 2. Pattern-based fallback identification if courier name not returned by API
    if not courier_name or courier_name == 'Courier Partner':
        awb_upper = awb.upper()
        if awb_upper.startswith('SF'):
            courier_code = 'shadowfax'
        elif re.match(r'^E[A-Z][0-9]{9}IN$', awb_upper):
            courier_code = 'indiapost'
        elif awb_upper.startswith('FMPC') or awb_upper.startswith('EKART'):
            courier_code = 'ekart'
        elif awb_upper.startswith('TBA'):
            courier_code = 'amazon'
        elif re.match(r'^[DZ][0-9]{8}$', awb_upper):
            courier_code = 'dtdc'
        elif awb.isdigit():
            if len(awb) == 10:
                courier_code = 'dhl'
            elif len(awb) == 11:
                courier_code = 'bluedart'
            elif len(awb) == 12:
                courier_code = 'fedex'
            elif len(awb) in [13, 14]:
                courier_code = 'delhivery'
        
        if courier_code and courier_code in COURIER_PARTNERS:
            meta = COURIER_PARTNERS[courier_code]
            courier_name = meta['name']
            if not track_url:
                track_url = generate_tracking_url(courier_code, awb)

    if not courier_code and courier_name:
        courier_code = normalize_courier_code(courier_name)

    if not track_url and (courier_code or courier_name):
        track_url = generate_tracking_url(courier_code or courier_name, awb)

    courier_meta = get_courier_metadata(courier_code or courier_name or 'custom')

    return jsonify({
        'success': True,
        'awb': awb,
        'courier_name': courier_name or courier_meta.get('name') or 'Courier Partner',
        'courier_code': courier_code or courier_meta.get('code') or 'custom',
        'tracking_url': track_url or generate_tracking_url(courier_meta.get('code', 'custom'), awb),
        'edd': edd or '',
        'origin': origin or '',
        'destination': destination or '',
        'current_status': current_status or 'Ready for Pickup',
        'courier_meta': courier_meta,
        'raw_data': raw_data
    })
