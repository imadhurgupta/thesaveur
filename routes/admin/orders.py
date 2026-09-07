import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from database import get_db
from services.couriers_service import generate_tracking_url, get_courier_metadata, get_courier_list
from services.auth_service import admin_required
from services.email_service import queue_order_status_update_email

admin_orders_bp = Blueprint('admin_orders_bp', __name__)


@admin_orders_bp.route('/admin/update-order-status/<order_ref>', methods=['POST'], endpoint='admin_update_order_status')
@admin_required
def admin_update_order_status(order_ref):
    if request.is_json:
        data = request.json or {}
    else:
        data = request.form or {}

    status = data.get('status', '').strip()
    courier_partner = data.get('courier_partner', '').strip() if 'courier_partner' in data else None
    custom_courier_name = (data.get('custom_courier_name') or '').strip()
    tracking_number = data.get('tracking_number', '').strip() if 'tracking_number' in data else None
    custom_tracking_url = data.get('tracking_url', '').strip() if 'tracking_url' in data else None
    estimated_delivery_date = data.get('estimated_delivery_date', '').strip() if 'estimated_delivery_date' in data else None
    save_courier_permanently = data.get('save_courier_permanently', False)

    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    current_order = db.execute(
        """
        SELECT * FROM orders 
        WHERE (order_number = ? OR id = ? OR order_number = ?)
        LIMIT 1
        """,
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()

    if not current_order:
        db.close()
        if request.is_json:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        flash("Order not found.", "error")
        return redirect(url_for('admin_dashboard'))

    order_id = current_order['id']
    VALID_STATUSES = ['Order Confirmed', 'Processing', 'Shipped', 'In Transit', 'Out for Delivery', 'Delivered', 'Cancelled']

    # Auto-detect courier & extract AWB from courier link if needed
    from services.couriers_service import detect_courier_info
    detected = detect_courier_info(custom_tracking_url or courier_partner or '', tracking_number or '')

    final_awb = tracking_number if tracking_number is not None and tracking_number.strip() else (detected.get('awb') or current_order['tracking_number'] or '')

    # Determine courier partner
    if custom_courier_name and custom_courier_name.strip():
        final_courier = custom_courier_name.strip()
    elif courier_partner and courier_partner not in ['__custom__', 'custom', '']:
        final_courier = courier_partner
    elif detected.get('name') and detected.get('code') != 'custom':
        final_courier = detected['name']
    else:
        final_courier = current_order['courier_partner'] or 'Courier Partner'

    final_edd = estimated_delivery_date if estimated_delivery_date is not None and estimated_delivery_date.strip() else (current_order['estimated_delivery_date'] or '')

    # If AWB is entered and courier partner is not explicitly set, fetch complete information from API
    if final_awb and (not final_courier or final_courier in ['Courier Partner', '', '__custom__', 'custom']):
        try:
            from services.tracking_service import ShiprocketClient
            client = ShiprocketClient()
            track_res = client.track_awb(final_awb)
            if track_res.get('success') and track_res.get('courier_name'):
                final_courier = track_res['courier_name']
                if not custom_tracking_url:
                    custom_tracking_url = track_res.get('track_url') or f"https://shiprocket.co/tracking/{final_awb}"
        except Exception as e:
            print(f"[AWB FETCH PARTNER ERROR] {e}")

    # Default tracking URL for all Shiprocket couriers
    if final_awb and not custom_tracking_url:
        custom_tracking_url = f"https://shiprocket.co/tracking/{final_awb}"

    # Auto-advance status to 'Shipped' when tracking number/AWB is entered
    if final_awb:
        if not status or status in ['Processing', 'Order Confirmed', 'Placed', '']:
            status = 'Shipped'

    # If status not specified, retain current
    if not status:
        status = current_order['status']
    elif status not in VALID_STATUSES:
        db.close()
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        flash("Invalid order status.", "error")
        return redirect(url_for('admin_dashboard'))

    # Strict workflow rule: Once shipped or in transit, cancellation is NOT available
    if status == 'Cancelled' and current_order['status'] in ['Shipped', 'In Transit', 'Out for Delivery', 'Delivered']:
        db.close()
        msg = "Order cannot be cancelled once it has been shipped."
        if request.is_json:
            return jsonify({'success': False, 'error': msg}), 400
        flash(msg, "error")
        return redirect(url_for('admin_order_detail', order_ref=current_order['order_number'] if current_order['order_number'] else order_id))

    # Save to custom_couriers table if requested
    if save_courier_permanently and custom_courier_name:
        c_code = re.sub(r'[^a-zA-Z0-9_]', '', custom_courier_name.lower().replace(' ', '_'))
        try:
            exists = db.execute("SELECT id FROM custom_couriers WHERE code = ? OR LOWER(name) = LOWER(?)", (c_code, custom_courier_name)).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO custom_couriers (name, code, url_pattern, sample_format) VALUES (?, ?, ?, ?)",
                    (custom_courier_name, c_code, custom_tracking_url or '{tracking_number}', 'Enter tracking number')
                )
                db.commit()
        except Exception as ce:
            print(f"[CUSTOM COURIER SAVE ERROR] {ce}")

    # Compute official tracking URL
    if custom_tracking_url and custom_tracking_url.strip():
        final_tracking_url = generate_tracking_url(final_courier, final_awb, custom_url=custom_tracking_url.strip())
    elif final_awb:
        final_tracking_url = generate_tracking_url(final_courier, final_awb)
    else:
        final_tracking_url = current_order['tracking_url'] or ''

    old_status = current_order['status']

    # Shipped timestamp
    shipped_clause = ""
    if status in ['Shipped', 'In Transit', 'Out for Delivery', 'Delivered'] and not current_order['shipped_at']:
        shipped_clause = ", shipped_at = CURRENT_TIMESTAMP"

    db.execute(
        f"""
        UPDATE orders 
        SET status = ?, 
            courier_partner = ?, 
            tracking_number = ?, 
            tracking_url = ?, 
            estimated_delivery_date = ?
            {shipped_clause}
        WHERE id = ?
        """,
        (status, final_courier, final_awb, final_tracking_url, final_edd, order_id)
    )
    
    # If the admin changes status to something other than Cancelled, clear any existing refund data
    if status != 'Cancelled' and current_order.get('refund_id'):
        db.execute(
            """
            UPDATE orders 
            SET refund_id = NULL,
                refund_status = NULL,
                refund_amount = NULL,
                refund_created_at = NULL
            WHERE id = ?
            """,
            (order_id,)
        )
        
    db.commit()
    db.close()

    # ── Cancellation & Refund Processing ──────────────────────────────────
    refund_info = {}
    if status == 'Cancelled':
        from services.refund_service import process_order_cancellation_refund
        refund_info = process_order_cancellation_refund(order_id, reason="Admin order cancellation", host_url=request.host_url)

    # Send status email notification if not cancelled (refund service handles cancellation email)
    if status != 'Cancelled':
        try:
            queue_order_status_update_email(order_id, status, host_url=request.host_url)
        except Exception as mail_err:
            print(f"[MAIL ALERT ERROR] Failed to send status update email: {mail_err}")

    if request.is_json:
        courier_meta = get_courier_metadata(final_courier)
        return jsonify({
            'success': True,
            'status': status,
            'courier_partner': final_courier,
            'courier_name': courier_meta['name'],
            'tracking_number': final_awb,
            'tracking_url': final_tracking_url,
            'estimated_delivery_date': final_edd,
            'refund_id': refund_info.get('refund_id'),
            'refund_status': refund_info.get('refund_status'),
            'is_cod': refund_info.get('is_cod', False)
        })

    label = current_order['order_number'] if current_order['order_number'] else f'#{order_id}'
    flash(f"Order {label} updated successfully.", "success")
    return redirect(url_for('admin_order_detail', order_ref=current_order['order_number'] if current_order['order_number'] else order_id))


@admin_orders_bp.route('/api/admin/orders/<int:order_id>/live-tracking-status', methods=['GET', 'POST'], endpoint='api_admin_order_live_tracking_status')
@admin_required
def api_admin_order_live_tracking_status(order_id):
    """Real-time live courier tracking status & refund details API for Admin Panel."""
    from services.tracking_service import get_order_live_tracking_status
    force = request.args.get('force', '1') in ['1', 'true', 'True']
    data = get_order_live_tracking_status(order_id, force_refresh=force, host_url=request.host_url)
    return jsonify(data)



@admin_orders_bp.route('/admin/orders/<order_ref>', endpoint='admin_order_detail')
@admin_required
def admin_order_detail(order_ref):
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT o.*,
               COALESCE(u.full_name, o.contact_name, 'Customer') AS user_name,
               COALESCE(u.email, o.contact_email, 'N/A') AS user_email
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        WHERE (o.order_number = ? OR o.id = ? OR o.order_number = ?)
          AND o.status != 'Pending Payment'
        LIMIT 1
        """,
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()

    if not order:
        db.close()
        flash(f"Order '{order_ref}' not found or payment has not been completed.", "error")
        return redirect(url_for('admin_dashboard'))

    items = db.execute(
        """
        SELECT oi.*,
               p.name           AS product_name,
               p.unit           AS unit,
               COALESCE(
                   (SELECT pi.image_filename FROM product_images pi
                    WHERE pi.product_id = p.id LIMIT 1),
                   p.image_filename
               ) AS image_filename
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
        """,
        (order['id'],)
    ).fetchall()

    db.close()

    from services.tracking_service import get_order_live_tracking, update_order_from_tracking

    couriers_list = get_courier_list()
    courier_meta = get_courier_metadata(order['courier_partner'])
    official_tracking_url = order['tracking_url'] or generate_tracking_url(order['courier_partner'], order['tracking_number'])
    live_tracking = get_order_live_tracking(order['id'])

    courier_url_map = {}
    for c in couriers_list:
        courier_url_map[c['code']] = c.get('url_pattern', '{awb}')
        courier_url_map[c['name']] = c.get('url_pattern', '{awb}')

    return render_template(
        'admin/order_detail.html',
        order=order,
        items=items,
        couriers=couriers_list,
        courier_meta=courier_meta,
        courier_url_map=courier_url_map,
        official_tracking_url=official_tracking_url,
        live_tracking=live_tracking
    )


@admin_orders_bp.route('/admin/orders/<order_ref>/sync-tracking', methods=['POST'], endpoint='admin_sync_order_tracking')
@admin_required
def admin_sync_order_tracking(order_ref):
    """On-demand manual Shiprocket live tracking sync for an order from the admin console."""
    clean_ref = str(order_ref).lstrip('#').strip()
    db = get_db()
    order = db.execute(
        """
        SELECT * FROM orders 
        WHERE (order_number = ? OR id = ? OR order_number = ?)
        LIMIT 1
        """,
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()
    db.close()

    if not order:
        return jsonify({'success': False, 'error': 'Order not found.'}), 404

    from services.tracking_service import update_order_from_tracking, get_order_live_tracking
    sync_result = update_order_from_tracking(order['id'], host_url=request.host_url)
    live_tracking = get_order_live_tracking(order['id'])

    db = get_db()
    refreshed_order = db.execute("SELECT * FROM orders WHERE id = ?", (order['id'],)).fetchone()
    db.close()

    refund_info = {}
    if refreshed_order and refreshed_order['status'] == 'Cancelled':
        refund_info = {
            'refund_id': refreshed_order['refund_id'],
            'refund_status': refreshed_order['refund_status'],
            'refund_amount': refreshed_order['refund_amount'],
            'payment_method': refreshed_order['payment_method']
        }

    target_st = (refreshed_order['status'] if refreshed_order else None) or sync_result.get('new_status')

    return jsonify({
        'success': sync_result.get('success', False),
        'changed': sync_result.get('changed', False),
        'old_status': sync_result.get('old_status'),
        'new_status': target_st,
        'status': target_st,
        'raw_courier_status': sync_result.get('raw_courier_status', ''),
        'live_tracking': live_tracking,
        'refund_info': refund_info,
        'error': sync_result.get('error')
    })


@admin_orders_bp.route('/admin/orders/<order_ref>/invoice', endpoint='admin_invoice')
@admin_required
def admin_invoice(order_ref):
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT o.*,
               COALESCE(u.full_name, o.contact_name, 'Customer') AS user_name,
               COALESCE(u.email, o.contact_email, 'N/A') AS user_email
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        WHERE (o.order_number = ? OR o.id = ? OR o.order_number = ?)
          AND o.status != 'Pending Payment'
        LIMIT 1
        """,
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()

    if not order:
        db.close()
        flash(f"Order '{order_ref}' not found or payment has not been completed.", "error")
        return redirect(url_for('admin_dashboard'))

    items = db.execute(
        """
        SELECT oi.*,
               p.name AS product_name,
               p.unit AS unit,
               p.gst_rate AS gst_rate
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
        """,
        (order['id'],)
    ).fetchall()

    db.close()

    return render_template(
        'invoice.html',
        order=order,
        items=items,
        back_url=url_for('admin_order_detail', order_ref=order['order_number'] if order['order_number'] else order['id']),
        back_label='Back to Order Detail',
        viewer='admin'
    )
