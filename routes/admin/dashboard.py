import os
from flask import Blueprint, render_template, redirect, url_for
from database import get_db
from services.auth_service import admin_required

admin_dashboard_bp = Blueprint('admin_dashboard_bp', __name__)


@admin_dashboard_bp.route('/admin', endpoint='admin_redirect')
def admin_redirect():
    return redirect(url_for('admin_dashboard'))


@admin_dashboard_bp.route('/admin/dashboard', endpoint='admin_dashboard')
@admin_required
def admin_dashboard():
    db = get_db()

    # Get statistics
    total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_enquiries = db.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0]
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending_enquiries = db.execute("SELECT COUNT(*) FROM enquiries WHERE status = 'Pending'").fetchone()[0]
    total_stocks = db.execute("SELECT SUM(stocks) FROM products").fetchone()[0] or 0

    # Get lists
    products_raw = db.execute("SELECT * FROM products ORDER BY category, name").fetchall()
    products_list = []
    for p in products_raw:
        p_dict = dict(p)
        imgs = db.execute("SELECT image_filename FROM product_images WHERE product_id = ?", (p['id'],)).fetchall()
        p_dict['images'] = [img['image_filename'] for img in imgs]
        p_dict['images_csv'] = ", ".join(p_dict['images'])
        products_list.append(p_dict)

    enquiries_list = db.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()
    users_list = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()

    # Get all orders
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

    carousel_slides = db.execute("SELECT * FROM carousel_slides ORDER BY slide_order ASC").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
    subcategories = db.execute(
        "SELECT s.*, c.display_name as parent_category_name FROM subcategories s JOIN categories c ON s.category_name = c.name ORDER BY s.category_name, s.display_order"
    ).fetchall()
    promo_codes = db.execute("SELECT * FROM promo_codes ORDER BY created_at DESC").fetchall()
    shipping_rates = db.execute(
        "SELECT * FROM location_shipping_charges ORDER BY CASE WHEN UPPER(state) = 'DEFAULT' THEN 1 ELSE 0 END, state ASC"
    ).fetchall()

    db.close()

    return render_template(
        'admin/dashboard.html',
        total_products=total_products,
        total_enquiries=total_enquiries,
        total_users=total_users,
        pending_enquiries=pending_enquiries,
        total_stocks=total_stocks,
        products=products_list,
        enquiries=enquiries_list,
        users=users_list,
        orders=orders_list,
        carousel_slides=carousel_slides,
        categories=categories,
        subcategories=subcategories,
        promo_codes=promo_codes,
        shipping_rates=shipping_rates,
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "")
    )
