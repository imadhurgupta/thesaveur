from datetime import datetime
import json
from flask import Blueprint, request, jsonify
from database import get_db
from services.tracking_service import (
    map_shiprocket_status_to_order_status,
    STATUS_STAGE_WEIGHTS,
    get_system_setting
)

api_webhooks_bp = Blueprint('api_webhooks_bp', __name__)


@api_webhooks_bp.route('/api/webhooks/health', methods=['GET'], endpoint='webhook_health')
def webhook_health():
    """Generic webhook endpoint health check."""
    return jsonify({
        'status': 'active',
        'service': 'The Saveur Webhook Handler',
        'timestamp': datetime.now().isoformat()
    }), 200


@api_webhooks_bp.route('/api/webhooks/delivery/push', methods=['POST', 'GET'], endpoint='delivery_push_webhook')
@api_webhooks_bp.route('/api/webhooks/updates', methods=['POST', 'GET'], endpoint='webhook_updates')
@api_webhooks_bp.route('/api/webhooks/shiprocket/tracking', methods=['POST', 'GET'], endpoint='shiprocket_tracking_webhook')
def shiprocket_tracking_webhook():
    """
    Real-time push webhook endpoint for Shiprocket Courier Tracking Updates.
    Dispatched by Shiprocket automatically whenever a package is scanned, in transit,
    out for delivery, or delivered.
    Compliant with Shiprocket rules (no 'shiprocket', 'sr', 'kr' keywords in delivery/push).
    """
    # Handle GET/HEAD health pings from webhook testers
    if request.method == 'GET':
        return jsonify({
            'status': 'active',
            'message': 'The Saveur Webhook Endpoint is online and ready for POST updates.'
        }), 200

    # 1. Verify webhook secret token if configured
    webhook_secret = (get_system_setting('SHIPROCKET_WEBHOOK_TOKEN') or '').strip()
    if webhook_secret:
        auth_header = (
            request.headers.get('x-api-key') or 
            request.headers.get('X-Api-Key') or
            request.headers.get('x-shiprocket-token') or 
            request.headers.get('Authorization', '').replace('Bearer ', '') or
            request.args.get('token', '')
        ).strip()
        if auth_header and auth_header != webhook_secret:
            print(f"[SHIPROCKET WEBHOOK] Security token verification failed. Received: {auth_header}")
            return jsonify({'success': False, 'error': 'Unauthorized webhook token.'}), 401

    payload = request.get_json(silent=True) or {}
    if not payload and request.form:
        payload = request.form.to_dict()

    # Handle test webhooks sent by Shiprocket dashboard during setup
    if not payload:
        return jsonify({'success': True, 'message': 'Webhook test connection verified successfully.'}), 200

    print(f"[SHIPROCKET WEBHOOK] Received payload: {json.dumps(payload)[:300]}...")

    # Extract tracking details from varying Shiprocket webhook structures
    tracking_data = payload.get('tracking_data') or payload.get('data') or payload

    raw_awb = (
        tracking_data.get('awb') or 
        tracking_data.get('awb_code') or 
        payload.get('awb') or 
        payload.get('awb_code') or ''
    )
    awb = str(raw_awb).strip()

    channel_order_id = str(
        tracking_data.get('channel_order_id') or 
        payload.get('channel_order_id') or ''
    ).strip()

    order_ref = str(
        tracking_data.get('order_id') or 
        payload.get('order_id') or 
        tracking_data.get('order_number') or 
        payload.get('order_number') or ''
    ).strip()

    raw_status = str(
        tracking_data.get('current_status') or 
        payload.get('current_status') or 
        tracking_data.get('shipment_status') or 
        payload.get('shipment_status') or 
        tracking_data.get('status') or ''
    ).strip()

    status_code = (
        tracking_data.get('current_status_id') or 
        payload.get('current_status_id') or 
        tracking_data.get('shipment_status_id') or 
        payload.get('shipment_status_id') or 
        tracking_data.get('shipment_status') or 
        payload.get('shipment_status')
    )

    raw_courier = str(
        tracking_data.get('courier_name') or 
        payload.get('courier_name') or ''
    ).strip()
    courier_name = '' if raw_courier.lower() in ['enter courier_name', 'enter your courier name', 'none', 'null'] else raw_courier

    edd = str(
        tracking_data.get('etd') or 
        tracking_data.get('edd') or 
        payload.get('etd') or 
        payload.get('edd') or ''
    ).strip()

    # Locate order in database
    db = get_db()
    order = None

    # 1. Search by AWB tracking number
    if awb and awb not in ['0', 'None', 'null']:
        order = db.execute("SELECT * FROM orders WHERE tracking_number = ? LIMIT 1", (awb,)).fetchone()

    # 2. Search by channel_order_id (Merchant's Store Order Number)
    if not order and channel_order_id and channel_order_id.lower() not in ['enter your channel order id', 'none', 'null', '']:
        clean_channel = channel_order_id.lstrip('#').strip()
        order = db.execute(
            """
            SELECT * FROM orders 
            WHERE (order_number = ? OR id = ? OR order_number = ?)
            LIMIT 1
            """,
            (channel_order_id, int(clean_channel) if clean_channel.isdigit() else -1, f"#{clean_channel}")
        ).fetchone()

    # 3. Search by order_id / order_number reference
    if not order and order_ref and order_ref.lower() not in ['enter your order id', 'none', 'null', '']:
        clean_ref = order_ref.lstrip('#').strip()
        order = db.execute(
            """
            SELECT * FROM orders 
            WHERE (order_number = ? OR id = ? OR order_number = ?)
            LIMIT 1
            """,
            (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
        ).fetchone()

    if not order:
        db.close()
        print(f"[SHIPROCKET WEBHOOK] Order not found for AWB='{awb}', Channel='{channel_order_id}', Ref='{order_ref}'. Acknowledging reception.")
        return jsonify({
            'success': True,
            'message': f"Order not found for AWB '{awb}', webhook acknowledged successfully."
        }), 200

    order_id = order['id']
    old_status = order['status']
    new_status = map_shiprocket_status_to_order_status(raw_status, status_code)

    old_weight = STATUS_STAGE_WEIGHTS.get(old_status, 1)
    new_weight = STATUS_STAGE_WEIGHTS.get(new_status, 1)

    status_changed = False
    final_status = old_status

    if new_status == 'Cancelled' and old_status != 'Cancelled':
        final_status = 'Cancelled'
        status_changed = True
    elif new_weight > old_weight:
        final_status = new_status
        status_changed = True
    elif old_status == 'Processing' and new_weight >= 2:
        final_status = new_status
        status_changed = True

    # Normalize scan activities
    raw_scans = tracking_data.get('scans') or tracking_data.get('shipment_track_activities') or []
    activities_clean = []
    if isinstance(raw_scans, list):
        for s in raw_scans:
            activities_clean.append({
                'activity': s.get('activity') or s.get('status') or raw_status,
                'location': s.get('location') or s.get('city') or '',
                'date': s.get('date') or s.get('time') or datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status': s.get('status') or ''
            })

    # Prepare tracking JSON string
    existing_json = {}
    if order['tracking_data_json']:
        try:
            existing_json = json.loads(order['tracking_data_json'])
        except Exception:
            pass

    combined_activities = activities_clean or existing_json.get('shipment_track_activities', [])

    tracking_json_str = json.dumps({
        'current_status': raw_status or existing_json.get('current_status', ''),
        'courier_name': courier_name or existing_json.get('courier_name', ''),
        'edd': edd or existing_json.get('edd', ''),
        'origin': existing_json.get('origin', ''),
        'destination': existing_json.get('destination', ''),
        'shipment_track': existing_json.get('shipment_track', []),
        'shipment_track_activities': combined_activities,
        'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'webhook'
    })

    edd_to_save = edd or order['estimated_delivery_date'] or ''
    courier_to_save = courier_name or order['courier_partner'] or ''

    db.execute(
        """
        UPDATE orders
        SET status = ?,
            tracking_status_raw = ?,
            tracking_data_json = ?,
            estimated_delivery_date = ?,
            courier_partner = ?,
            last_tracking_fetch = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (final_status, raw_status, tracking_json_str, edd_to_save, courier_to_save, order_id)
    )
    db.commit()
    db.close()

    if status_changed:
        try:
            from services.email_service import queue_order_status_update_email
            queue_order_status_update_email(order_id, final_status, host_url=request.host_url)
            print(f"[SHIPROCKET WEBHOOK] Order #{order_id} advanced to '{final_status}'. Notification email sent.")
        except Exception as mail_err:
            print(f"[SHIPROCKET WEBHOOK ERROR] Email dispatch failed: {mail_err}")

    return jsonify({
        'success': True,
        'message': f"Order #{order_id} updated successfully.",
        'order_id': order_id,
        'old_status': old_status,
        'new_status': final_status,
        'status_changed': status_changed
    }), 200
