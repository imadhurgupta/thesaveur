from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db
from services.couriers_service import generate_tracking_url, get_courier_metadata, get_courier_list
from services.auth_service import verify_order_access

orders_bp = Blueprint('orders', __name__)


@orders_bp.route('/my-orders', endpoint='my_orders')
def my_orders():
    if 'user_id' not in session:
        flash("Please log in to view your orders.", "error")
        return redirect(url_for('login'))

    db = get_db()
    orders_raw = db.execute(
        "SELECT * FROM orders WHERE user_id = ? AND status != 'Pending Payment' ORDER BY created_at DESC", 
        (session['user_id'],)
    ).fetchall()

    orders_list = []
    for order in orders_raw:
        o_dict = dict(order)
        items = db.execute(
            """
            SELECT oi.*, p.name as product_name, p.image_filename 
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
            """,
            (order['id'],)
        ).fetchall()
        o_dict['items'] = [dict(item) for item in items]
        orders_list.append(o_dict)

    db.close()
    return render_template('my_orders.html', orders=orders_list)


@orders_bp.route('/track-order', methods=['GET', 'POST'], endpoint='track_order')
@orders_bp.route('/track-order/<order_ref>', endpoint='track_order')
def track_order(order_ref=None):
    """
    Secure live tracking page for customers.
    Strictly verifies customer ownership (logged-in account, admin role, or cryptographic HMAC token).
    """
    db = get_db()
    search_query = ''
    order = None

    if order_ref is None:
        ref = (request.values.get('order_number') or request.values.get('order_id') or request.values.get('ref') or '').strip()
        search_query = ref
        if ref:
            clean_ref = ref.lstrip('#').strip()
            order = db.execute(
                """
                SELECT o.*, u.full_name as customer_name, u.email as customer_email, u.phone as customer_phone
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE (o.order_number = ? OR o.id = ? OR o.order_number = ?) AND o.status != 'Pending Payment'
                LIMIT 1
                """,
                (ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
            ).fetchone()

            if not order:
                db.close()
                flash(f"No order found matching '{ref}'. Please check your Order ID.", "error")
                return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query=search_query)
        else:
            db.close()
            return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query='')
    else:
        clean_ref = str(order_ref).lstrip('#').strip()
        order = db.execute(
            """
            SELECT o.*, u.full_name as customer_name, u.email as customer_email, u.phone as customer_phone
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE (o.order_number = ? OR o.id = ? OR o.order_number = ?) AND o.status != 'Pending Payment'
            LIMIT 1
            """,
            (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}")
        ).fetchone()

        if not order:
            db.close()
            flash(f"Order '{order_ref}' not found.", "error")
            return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query=str(order_ref))

    # Strict ownership authentication check
    is_authorized, auth_msg = verify_order_access(order, session, request)
    if not is_authorized:
        db.close()
        if 'user_id' not in session:
            flash("Security Verification: Please log in to your account to view this order's tracking details.", "error")
            return redirect(url_for('login', next=request.full_path if request.full_path else request.path))
        else:
            flash("Access Denied: You are not authorized to view tracking details for another customer's order.", "error")
            return redirect(url_for('my_orders'))

    order_id = order['id']
    items = db.execute(
        """
        SELECT oi.*, p.name as product_name, p.unit as unit,
               COALESCE(
                   (SELECT pi.image_filename FROM product_images pi
                    WHERE pi.product_id = p.id LIMIT 1),
                   p.image_filename
               ) AS image_filename
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
        """,
        (order_id,)
    ).fetchall()

    db.close()

    courier_meta = get_courier_metadata(order['courier_partner'])
    official_tracking_url = order['tracking_url'] or generate_tracking_url(order['courier_partner'], order['tracking_number'])

    return render_template(
        'track_order.html',
        order=order,
        items=items,
        courier_meta=courier_meta,
        official_tracking_url=official_tracking_url,
        search_query=search_query or (order['order_number'] or str(order['id']))
    )


@orders_bp.route('/orders/<order_ref>/invoice', endpoint='customer_invoice')
def customer_invoice(order_ref):
    """Render single-page secure tax invoice with strict customer ownership authentication."""
    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT o.*,
               u.full_name AS user_name,
               u.email     AS user_email,
               u.phone     AS user_phone
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
        flash("Invoice not found or payment is incomplete.", "error")
        return redirect(url_for('my_orders') if 'user_id' in session else url_for('home'))

    # Verify authorization
    is_authorized, auth_msg = verify_order_access(order, session, request)
    if not is_authorized:
        db.close()
        if 'user_id' not in session:
            flash("Please log in to your account to securely view your invoice.", "error")
            return redirect(url_for('login', next=request.full_path if request.full_path else request.path))
        else:
            flash("Access Denied: You do not have permission to view this invoice.", "error")
            return redirect(url_for('my_orders'))

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
        back_url=url_for('my_orders') if 'user_id' in session else url_for('home'),
        back_label='Back to My Orders' if 'user_id' in session else 'Back to Home',
        viewer='customer'
    )


@orders_bp.route('/orders/<order_ref>/cancel', methods=['POST'], endpoint='customer_cancel_order')
def customer_cancel_order(order_ref):
    """Allow customer to cancel their order before it is shipped, reversing product stock."""
    if 'user_id' not in session:
        flash('Please log in to manage your order.', 'error')
        return redirect(url_for('login'))

    db = get_db()
    clean_ref = str(order_ref).lstrip('#').strip()
    order = db.execute(
        """
        SELECT * FROM orders 
        WHERE (order_number = ? OR id = ? OR order_number = ?) 
          AND user_id = ?
        LIMIT 1
        """,
        (order_ref, int(clean_ref) if clean_ref.isdigit() else -1, f"#{clean_ref}", session['user_id'])
    ).fetchone()

    if not order:
        db.close()
        flash("Order not found.", "error")
        return redirect(url_for('my_orders'))

    if order['status'] != 'Processing':
        db.close()
        flash(f"Order cannot be cancelled because it is already {order['status'].lower()}.", "error")
        return redirect(url_for('my_orders'))

    order_id = order['id']

    # Reverse stock back to products
    order_items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in order_items:
        db.execute("UPDATE products SET stocks = stocks + ? WHERE id = ?", (item['quantity'], item['product_id']))

    db.execute("UPDATE orders SET status = 'Cancelled' WHERE id = ?", (order_id,))
    db.commit()
    db.close()

    try:
        from services.email_service import queue_order_status_update_email
        queue_order_status_update_email(order_id, 'Cancelled')
    except Exception as mail_err:
        print(f"[MAIL ERROR] Failed to send customer cancel email: {mail_err}")

    flash(f"Order #{order['order_number'] or order_id} has been successfully cancelled and stocks restored.", "success")
    return redirect(url_for('my_orders'))

