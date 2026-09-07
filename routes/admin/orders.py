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

    # Fallback to existing values if not provided
    if courier_partner in ['__custom__', 'custom', ''] and custom_courier_name:
        final_courier = custom_courier_name
    elif courier_partner is not None:
        final_courier = courier_partner
    else:
        final_courier = current_order['courier_partner'] or ''

    final_awb = tracking_number if tracking_number is not None else (current_order['tracking_number'] or '')
    final_edd = estimated_delivery_date if estimated_delivery_date is not None else (current_order['estimated_delivery_date'] or '')

    # Auto-change status to 'Shipped' when courier partner & tracking number are provided
    if final_courier and final_awb:
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
    if custom_tracking_url:
        final_tracking_url = generate_tracking_url(final_courier, final_awb, custom_url=custom_tracking_url)
    elif final_awb:
        final_tracking_url = generate_tracking_url(final_courier, final_awb)
    elif custom_tracking_url is not None:
        final_tracking_url = ''
    else:
        final_tracking_url = current_order['tracking_url'] or ''

    old_status = current_order['status']

    # ── Stock Management on Status Change ─────────────────────────────────────
    # 1. Reverse stock when cancelling an order BEFORE it has been shipped
    if status == 'Cancelled' and old_status in ['Processing', 'Placed', 'Order Confirmed']:
        order_items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in order_items:
            db.execute("UPDATE products SET stocks = stocks + ? WHERE id = ?", (item['quantity'], item['product_id']))
        print(f"[STOCK REVERSED] Order #{order_id} cancelled from '{old_status}'. Restored stock for {len(order_items)} items.")

    # 2. Re-deduct stock if an order was 'Cancelled' and is reactivated back to an active state
    elif old_status == 'Cancelled' and status in ['Processing', 'Placed', 'Order Confirmed', 'Shipped', 'In Transit', 'Out for Delivery', 'Delivered']:
        order_items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in order_items:
            db.execute("UPDATE products SET stocks = stocks - ? WHERE id = ?", (item['quantity'], item['product_id']))
        print(f"[STOCK DEDUCTED] Order #{order_id} reactivated to '{status}'. Deducted stock for {len(order_items)} items.")

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
    db.commit()
    db.close()

    # Send status email notification
    try:
        queue_order_status_update_email(order_id, status, host_url=request.host_url)
    except Exception as mail_err:
        print(f"[MAIL ALERT ERROR] Failed to send status update email: {mail_err}")

    # Broadcast real-time delivery status update to all connected customers and admin screens
    try:
        from services.tracking_service import broadcast_tracking_update, get_tracking_events
        events = get_tracking_events(order_id)
        c_meta = get_courier_metadata(final_courier)
        broadcast_tracking_update(order_id, {
            'order_id': order_id,
            'status': status,
            'courier_partner': final_courier,
            'courier_name': c_meta['name'] if c_meta else '',
            'tracking_number': final_awb,
            'tracking_url': final_tracking_url,
            'estimated_delivery_date': final_edd,
            'tracking_events': events
        })
    except Exception as b_err:
        print(f"[BROADCAST ERROR] {b_err}")

    if request.is_json:
        courier_meta = get_courier_metadata(final_courier)
        return jsonify({
            'success': True,
            'status': status,
            'courier_partner': final_courier,
            'courier_name': courier_meta['name'],
            'tracking_number': final_awb,
            'tracking_url': final_tracking_url,
            'estimated_delivery_date': final_edd
        })

    label = current_order['order_number'] if current_order['order_number'] else f'#{order_id}'
    flash(f"Order {label} updated successfully.", "success")
    return redirect(url_for('admin_order_detail', order_ref=current_order['order_number'] if current_order['order_number'] else order_id))


@admin_orders_bp.route('/admin/orders/<order_ref>', endpoint='admin_order_detail')
@admin_required
def admin_order_detail(order_ref):
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT o.*,
               u.full_name  AS user_name,
               u.email      AS user_email
        FROM orders o
        JOIN users u ON o.user_id = u.id
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

    couriers_list = get_courier_list()
    courier_meta = get_courier_metadata(order['courier_partner'])
    official_tracking_url = order['tracking_url'] or generate_tracking_url(order['courier_partner'], order['tracking_number'])

    courier_url_map = {}
    for c in couriers_list:
        courier_url_map[c['code']] = c.get('url_pattern', '{awb}')
        courier_url_map[c['name']] = c.get('url_pattern', '{awb}')

    from services.tracking_service import get_tracking_events, get_system_setting
    tracking_events = get_tracking_events(order['id'])
    shipglobal_email = get_system_setting('SHIPGLOBAL_EMAIL', '')
    shipglobal_pass = get_system_setting('SHIPGLOBAL_PASSWORD', '')
    shipglobal_service = get_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', 'DHLECS-CLASSIC')
    shipglobal_sandbox = get_system_setting('SHIPGLOBAL_SANDBOX_MODE', '0')
    shipglobal_token = get_system_setting('SHIPGLOBAL_API_TOKEN', '')
    has_shipglobal_creds = bool((shipglobal_email and shipglobal_pass) or shipglobal_token or (shipglobal_sandbox == '1'))

    from services.couriers_service import get_logistics_providers
    logistics_providers = get_logistics_providers()

    return render_template(
        'admin/order_detail.html',
        order=order,
        items=items,
        couriers=couriers_list,
        courier_meta=courier_meta,
        courier_url_map=courier_url_map,
        official_tracking_url=official_tracking_url,
        tracking_events=tracking_events,
        has_shipglobal_creds=has_shipglobal_creds,
        shipglobal_email=shipglobal_email,
        shipglobal_service=shipglobal_service,
        shipglobal_sandbox=shipglobal_sandbox,
        shipglobal_token=shipglobal_token,
        logistics_providers=logistics_providers
    )



@admin_orders_bp.route('/admin/orders/<order_ref>/invoice', endpoint='admin_invoice')
@admin_required
def admin_invoice(order_ref):
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT o.*,
               u.full_name AS user_name,
               u.email     AS user_email
        FROM orders o
        JOIN users u ON o.user_id = u.id
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


@admin_orders_bp.route('/admin/orders/<order_ref>/shipglobal-label', methods=['POST'], endpoint='admin_create_shipglobal_label')
@admin_required
def admin_create_shipglobal_label(order_ref):
    """
    Generate official international shipping label via ShipGlobal API (/api/v1/addOrder.php).
    Returns JSON with waybill_number and pdf_base64.
    """
    from services.tracking_service import create_shipglobal_shipment, get_system_setting

    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        "SELECT id FROM orders WHERE order_number = ? OR id = ? OR order_number = ?",
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()
    db.close()

    if not order:
        return jsonify({'success': False, 'error': 'Order not found'}), 404

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    service_code = data.get('service_code') or get_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', 'DHLECS-CLASSIC')

    res = create_shipglobal_shipment(order['id'], service_code=service_code, host_url=request.host_url)
    return jsonify(res)


@admin_orders_bp.route('/admin/orders/<order_ref>/download-shipping-label', methods=['GET'], endpoint='admin_download_shipping_label')
@admin_required
def admin_download_shipping_label(order_ref):
    """Download stored ShipGlobal Base64 decoded PDF shipping label."""
    import base64
    from flask import Response
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        "SELECT order_number, id, shipping_label_pdf, tracking_number FROM orders WHERE order_number = ? OR id = ? OR order_number = ?",
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
    ).fetchone()
    db.close()

    if not order or not order['shipping_label_pdf']:
        flash('No shipping label found for this order.', 'error')
        return redirect(url_for('admin_order_detail', order_ref=order_ref))

    try:
        raw_b64 = order['shipping_label_pdf'].strip()
        if 'base64,' in raw_b64:
            raw_b64 = raw_b64.split('base64,')[1]
        pdf_bytes = base64.b64decode(raw_b64)
    except Exception as b_err:
        flash(f'Failed to decode shipping label PDF: {b_err}', 'error')
        return redirect(url_for('admin_order_detail', order_ref=order_ref))

    filename = f"ShipGlobal_Label_{order['tracking_number'] or order['order_number'] or order['id']}.pdf"
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'inline; filename="{filename}"'
        }
    )
