from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db
from services.couriers_service import generate_tracking_url, get_courier_metadata, get_courier_list

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
@orders_bp.route('/track-order/<int:order_id>', endpoint='track_order')
def track_order(order_id=None):
    """Public live tracking page for customers."""
    db = get_db()
    search_query = ''

    if order_id is None:
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
            if order:
                order_id = order['id']
            else:
                db.close()
                flash(f"No order found matching '{ref}'. Please check your Order ID or tracking reference.", "error")
                return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query=search_query)
        else:
            db.close()
            return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query='')

    order = db.execute(
        """
        SELECT o.*, u.full_name as customer_name, u.email as customer_email, u.phone as customer_phone
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ? AND o.status != 'Pending Payment'
        """,
        (order_id,)
    ).fetchone()

    if not order:
        db.close()
        flash(f"Order #{order_id} not found.", "error")
        return render_template('track_order.html', order=None, items=[], couriers=get_courier_list(), search_query=str(order_id))

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


@orders_bp.route('/orders/<int:id>/invoice', endpoint='customer_invoice')
def customer_invoice(id):
    if 'user_id' not in session:
        flash('Please log in to view your invoice.', 'error')
        return redirect(url_for('login'))

    db = get_db()
    order = db.execute(
        """
        SELECT o.*,
               u.full_name AS user_name,
               u.email     AS user_email
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ? AND o.user_id = ? AND o.status != 'Pending Payment'
        """,
        (id, session['user_id'])
    ).fetchone()

    if not order:
        db.close()
        flash("Invoice not found or you don't have permission to view it.", "error")
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
        (id,)
    ).fetchall()
    db.close()

    return render_template(
        'invoice.html',
        order=order,
        items=items,
        back_url=url_for('my_orders'),
        back_label='Back to My Orders',
        viewer='customer'
    )
