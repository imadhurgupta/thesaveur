import os
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import get_db

api_webhooks_bp = Blueprint('api_webhooks_bp', __name__)


@api_webhooks_bp.route('/api/webhooks/health', methods=['GET'], endpoint='webhook_health')
def webhook_health():
    """Generic webhook endpoint health check."""
    return jsonify({
        'status': 'active',
        'service': 'The Saveur Webhook Handler',
        'timestamp': datetime.now().isoformat()
    }), 200


@api_webhooks_bp.route('/api/webhooks/tracking', methods=['POST'], endpoint='webhook_tracking')
def webhook_tracking():
    """
    Receive push tracking events from ANY delivery partner:
    Shiprocket, Delhivery, 17TRACK, TrackingMore, Blue Dart, DTDC, or custom webhooks.
    Verifies optional X-Webhook-Secret header, then instantly updates the matching order.
    Configure your courier dashboard to POST to: https://yourdomain.com/api/webhooks/tracking
    """
    from services.tracking_service import (
        parse_universal_webhook,
        get_system_setting, save_tracking_events, update_order_from_events
    )

    # Verify shared secret (if configured)
    expected_secret = get_system_setting('TRACKING_WEBHOOK_SECRET', '')
    if expected_secret:
        incoming = (
            request.headers.get('X-Webhook-Secret', '') or
            request.headers.get('x-webhook-secret', '') or
            request.headers.get('Authorization', '').replace('Bearer ', '').strip() or
            request.args.get('secret', '')
        )
        if incoming != expected_secret:
            return jsonify({'error': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    if not payload:
        return jsonify({'error': 'Empty payload'}), 400

    # Parse payload from any delivery partner
    event = parse_universal_webhook(payload)
    if not event:
        return jsonify({'error': 'Unrecognised payload format. Ensure payload includes AWB/tracking_number and status.'}), 422

    awb = event.get('awb', '').strip()
    if not awb:
        return jsonify({'error': 'No AWB/tracking number detected in payload'}), 422

    # Find order by AWB or by order_number / id
    db = get_db()
    order = db.execute(
        """SELECT id, status, courier_partner, tracking_number FROM orders 
           WHERE tracking_number = ? OR order_number = ? OR CAST(id AS TEXT) = ? 
           LIMIT 1""",
        (awb, awb, awb)
    ).fetchone()

    if not order:
        db.close()
        return jsonify({'error': 'Order not found for AWB or Reference', 'awb': awb}), 404

    order_id = order['id']
    courier  = order['courier_partner'] or 'Courier'

    events_to_save = [{
        'status_raw':    event['status_raw'],
        'status_mapped': event['status_mapped'],
        'location':      event.get('location', ''),
        'message':       event.get('message', ''),
        'event_time':    event.get('event_time', ''),
    }]

    best_status = save_tracking_events(db, order_id, courier, events_to_save)
    db.commit()
    db.close()

    changed = False
    if best_status:
        changed = update_order_from_events(order_id, best_status, host_url=request.host_url)

    if not changed:
        try:
            from services.tracking_service import broadcast_tracking_update, get_tracking_events
            from services.couriers_service import get_courier_metadata
            import time
            c_meta = get_courier_metadata(order['courier_partner'])
            broadcast_tracking_update(order_id, {
                'order_id': order_id,
                'status': best_status or order['status'],
                'courier_partner': order['courier_partner'] or '',
                'courier_name': c_meta['name'] if c_meta else (order['courier_partner'] or ''),
                'tracking_number': awb,
                'tracking_events': get_tracking_events(order_id),
                'timestamp': time.time(),
            })
        except Exception:
            pass

    print(f"[WEBHOOK] Order #{order_id} AWB={awb} -> {event['status_mapped']} (changed={changed})")
    return jsonify({
        'success': True,
        'order_id': order_id,
        'status': best_status or order['status'],
        'changed': changed,
        'raw_status': event['status_raw'],
    }), 200


