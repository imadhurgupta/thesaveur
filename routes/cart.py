from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db

cart_bp = Blueprint('cart', __name__)


@cart_bp.route('/cart', endpoint='view_cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0.0

    db = get_db()
    for prod_id, qty in cart.items():
        product = db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
        if product:
            p_dict = dict(product)
            discount_percent = product['discount_percent'] if product['discount_percent'] else 0.0
            price_paid = product['price']
            if discount_percent > 0:
                price_paid = round(product['price'] * (1 - discount_percent / 100), 2)
            p_dict['price'] = price_paid
            p_dict['original_price'] = product['price']
            p_dict['quantity'] = qty
            p_dict['item_total'] = price_paid * qty
            subtotal += p_dict['item_total']
            cart_items.append(p_dict)

    db.close()
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal)


@cart_bp.route('/cart/add/<product_id>', methods=['POST'], endpoint='add_to_cart')
def add_to_cart(product_id):
    try:
        qty = int(request.form.get('quantity', 1) or 1)
    except ValueError:
        qty = 1

    if qty <= 0:
        qty = 1

    db = get_db()
    product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (product_id,)).fetchone()
    db.close()

    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('products'))

    if product['stocks'] < qty:
        flash(f"Insufficient stock for {product['name']}. Only {product['stocks']} available.", "error")
        return redirect(request.referrer or url_for('products'))

    cart = session.get('cart', {})
    prod_id_str = str(product_id)
    cart[prod_id_str] = cart.get(prod_id_str, 0) + qty
    session['cart'] = cart
    session.modified = True

    # Buy Now: skip cart page, go directly to checkout
    if request.form.get('buy_now') == '1':
        flash(f"{product['name']} added. Complete your purchase below.", "success")
        return redirect(url_for('checkout'))

    flash(f"Added {qty} {product['name']} to cart.", "success")
    return redirect(url_for('view_cart'))


@cart_bp.route('/cart/update/<product_id>', methods=['POST'], endpoint='update_cart')
def update_cart(product_id):
    try:
        qty = int(request.form.get('quantity', 1) or 1)
    except ValueError:
        qty = 1

    cart = session.get('cart', {})
    prod_id_str = str(product_id)

    if qty <= 0:
        cart.pop(prod_id_str, None)
        flash("Item removed from cart.", "success")
    else:
        db = get_db()
        product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (product_id,)).fetchone()
        db.close()

        if product and product['stocks'] < qty:
            flash(f"Cannot update quantity. Only {product['stocks']} units in stock.", "error")
            return redirect(url_for('view_cart'))

        cart[prod_id_str] = qty
        flash("Cart updated.", "success")

    session['cart'] = cart
    session.modified = True
    return redirect(url_for('view_cart'))


@cart_bp.route('/cart/remove/<product_id>', methods=['POST'], endpoint='remove_from_cart')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    flash("Item removed from cart.", "success")
    return redirect(url_for('view_cart'))


@cart_bp.route('/wishlist/toggle/<product_id>', methods=['POST'], endpoint='toggle_wishlist')
def toggle_wishlist(product_id):
    """Add or remove a product from the session wishlist."""
    if 'user_id' not in session:
        flash("Please log in to save items to your wishlist.", "error")
        return redirect(url_for('login', next=request.referrer or url_for('products')))

    wishlist = session.get('wishlist', [])
    prod_str = str(product_id)

    if prod_str in [str(w) for w in wishlist]:
        wishlist = [w for w in wishlist if str(w) != prod_str]
        flash("Removed from your wishlist.", "info")
    else:
        wishlist.append(prod_str)
        flash("Added to your wishlist! ❤️", "success")

    session['wishlist'] = wishlist
    session.modified = True
    return redirect(request.referrer or url_for('product_detail', id=product_id))
