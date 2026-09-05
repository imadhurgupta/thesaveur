from datetime import datetime
import requests
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db
from services.auth_service import generate_order_number
from services.razorpay_service import get_razorpay_client
from services.paypal_service import get_paypal_api_base, get_paypal_access_token
from services.email_service import queue_order_confirmation_email
from core.config import RAZORPAY_KEY_ID, IS_REAL_MODE, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_EXCHANGE_RATE

checkout_bp = Blueprint('checkout', __name__)


@checkout_bp.route('/checkout', endpoint='checkout')
def checkout():
    if 'user_id' not in session:
        flash("Please log in to proceed to checkout.", "error")
        return redirect(url_for('login', next=request.url))

    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for('products'))

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

    user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    db.close()
    
    return render_template('checkout.html', cart_items=cart_items, subtotal=subtotal, user=user)


@checkout_bp.route('/checkout/submit', methods=['POST'], endpoint='checkout_submit')
def checkout_submit():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Session expired. Please log in again."}), 401

    cart = session.get('cart', {})
    if not cart:
        return jsonify({"success": False, "message": "Your cart is empty."}), 400

    shipping_address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    zip_code = request.form.get('zip', '').strip()
    contact_name = request.form.get('contact_name', '').strip()
    contact_email = request.form.get('contact_email', '').strip()
    contact_phone = request.form.get('contact_phone', '').strip()
    payment_method = request.form.get('payment_method', 'UPI').strip()
    promo_code_input = request.form.get('promo_code', '').strip().upper()

    if not shipping_address or not city or not state or not zip_code or not contact_name or not contact_email or not contact_phone:
        return jsonify({"success": False, "message": "Please fill in all shipping and contact details."}), 400

    db = get_db()
    try:
        total_amount = 0.0
        order_items_to_create = []

        for prod_id, qty in cart.items():
            product = db.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
            if not product:
                return jsonify({"success": False, "message": "One of the products in your cart is no longer available."}), 400

            if product['stocks'] < qty:
                return jsonify({"success": False, "message": f"Insufficient stock for {product['name']}. Only {product['stocks']} available."}), 400

            discount_percent = product['discount_percent'] if product['discount_percent'] else 0.0
            price_paid = product['price']
            if discount_percent > 0:
                price_paid = round(product['price'] * (1 - discount_percent / 100), 2)

            total_amount += price_paid * qty
            order_items_to_create.append({
                'product_id': product['id'],
                'product_name': product['name'],
                'quantity': qty,
                'price': price_paid,
                'original_price': product['price'],
                'discount_percent': discount_percent
            })

        # Validate and apply promo code
        applied_promo = None
        final_discount = 0.0
        if promo_code_input:
            promo = db.execute(
                "SELECT * FROM promo_codes WHERE UPPER(code) = ? AND is_active = 1",
                (promo_code_input,)
            ).fetchone()
            if promo:
                is_expired = False
                if promo['expires_at']:
                    try:
                        exp = datetime.fromisoformat(promo['expires_at'])
                        is_expired = datetime.utcnow() > exp
                    except Exception:
                        pass
                max_hit = promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']
                min_ok = total_amount >= promo['min_order_amount']
                if not is_expired and not max_hit and min_ok:
                    if promo['discount_type'] == 'percent':
                        final_discount = round(total_amount * promo['discount_value'] / 100, 2)
                    else:
                        final_discount = min(round(promo['discount_value'], 2), total_amount)
                    applied_promo = promo

        # Secure server-side calculation of shipping charges
        state_row = db.execute(
            "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = ?",
            (state.upper(),)
        ).fetchone()
        
        if state_row:
            location_charge = float(state_row['charge'])
        else:
            default_row = db.execute(
                "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = 'DEFAULT'"
            ).fetchone()
            location_charge = float(default_row['charge']) if default_row else 60.0

        product_shipping_total = 0.0
        for prod_id, qty in cart.items():
            product_sh = db.execute("SELECT shipping_charge FROM products WHERE id = ?", (prod_id,)).fetchone()
            if product_sh:
                product_shipping_total += float(product_sh['shipping_charge'] or 0.0) * int(qty)
                
        final_shipping_charge = location_charge + product_shipping_total
        final_total = round(total_amount - final_discount + final_shipping_charge, 2)
        order_number = generate_order_number()

        if payment_method == 'COD':
            cursor = db.execute(
                """INSERT INTO orders
                   (user_id, total_amount, shipping_address, city, state, zip_code,
                    payment_method, status, discount_amount, promo_code, order_number,
                    contact_name, contact_email, contact_phone, razorpay_order_id, shipping_charge)
                   VALUES (?, ?, ?, ?, ?, ?, 'COD', 'Processing', ?, ?, ?, ?, ?, ?, 'COD', ?)""",
                (session['user_id'], final_total, shipping_address, city, state, zip_code,
                 final_discount, applied_promo['code'] if applied_promo else '',
                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)
            )
            order_id = cursor.lastrowid

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )
                db.execute(
                    "UPDATE products SET stocks = stocks - ? WHERE id = ?",
                    (item['quantity'], item['product_id'])
                )

            if applied_promo:
                db.execute(
                    "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",
                    (applied_promo['code'].upper(),)
                )

            session.pop('cart', None)
            session.modified = True
            db.commit()

            try:
                queue_order_confirmation_email(
                    contact_email, contact_name, order_number, final_total,
                    f"{shipping_address}, {city}, {state} - {zip_code}",
                    order_items_to_create
                )
            except Exception as mail_err:
                print(f"[MAIL] Failed to send order confirmation email: {str(mail_err)}")

            return jsonify({
                "success": True,
                "cod": True,
                "redirect_url": url_for('my_orders')
            })

        elif payment_method == 'PayPal':
            cursor = db.execute(
                """INSERT INTO orders
                   (user_id, total_amount, shipping_address, city, state, zip_code,
                    payment_method, status, discount_amount, promo_code, order_number,
                    contact_name, contact_email, contact_phone, paypal_order_id, shipping_charge)
                   VALUES (?, ?, ?, ?, ?, ?, 'PayPal', 'Pending Payment', ?, ?, ?, ?, ?, ?, '', ?)""",
                (session['user_id'], final_total, shipping_address, city, state, zip_code,
                 final_discount, applied_promo['code'] if applied_promo else '',
                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)
            )
            order_id = cursor.lastrowid

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )

            token = get_paypal_access_token()
            paypal_ord_id = None
            usd_total = round(final_total * PAYPAL_EXCHANGE_RATE, 2)

            if token:
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    }
                    payload = {
                        "intent": "CAPTURE",
                        "purchase_units": [
                            {
                                "reference_id": order_number,
                                "amount": {
                                    "currency_code": "USD",
                                    "value": f"{usd_total:.2f}"
                                },
                                "description": f"Order {order_number} from The Saveur"
                            }
                        ]
                    }
                    url = f"{get_paypal_api_base()}/v2/checkout/orders"
                    res = requests.post(url, headers=headers, json=payload, timeout=10)
                    if res.status_code in (200, 201):
                        paypal_ord_id = res.json().get('id')
                    else:
                        print(f"[PAYPAL] Order creation failed: {res.status_code} - {res.text}")
                except Exception as py_err:
                    print(f"[PAYPAL] Order API error: {str(py_err)}")

            if not paypal_ord_id:
                paypal_ord_id = f"MOCK_PAYPAL_ORD_{order_number}"

            db.execute(
                "UPDATE orders SET paypal_order_id = ? WHERE id = ?",
                (paypal_ord_id, order_id)
            )
            db.commit()

            return jsonify({
                "success": True,
                "paypal": True,
                "order_id": order_id,
                "order_number": order_number,
                "paypal_order_id": paypal_ord_id,
                "amount_usd": f"{usd_total:.2f}",
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            })

        else:
            # Online Payment: Razorpay
            cursor = db.execute(
                """INSERT INTO orders
                   (user_id, total_amount, shipping_address, city, state, zip_code,
                    payment_method, status, discount_amount, promo_code, order_number,
                    contact_name, contact_email, contact_phone, razorpay_order_id, shipping_charge)
                   VALUES (?, ?, ?, ?, ?, ?, 'Online', 'Pending Payment', ?, ?, ?, ?, ?, ?, '', ?)""",
                (session['user_id'], final_total, shipping_address, city, state, zip_code,
                 final_discount, applied_promo['code'] if applied_promo else '',
                 order_number, contact_name, contact_email, contact_phone, final_shipping_charge)
            )
            order_id = cursor.lastrowid

            for item in order_items_to_create:
                db.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, price, original_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['product_id'], item['quantity'], item['price'], item['original_price'], item['discount_percent'])
                )

            rz_client = get_razorpay_client()
            rz_order_id = None

            if IS_REAL_MODE and not rz_client:
                raise Exception("Razorpay client is not configured. Real Mode is enabled.")

            if rz_client:
                try:
                    amount_paise = int(final_total * 100)
                    notes = {
                        "order_number": order_number,
                        "contact_name": contact_name,
                        "contact_email": contact_email
                    }
                    rz_order = rz_client.order.create(data={
                        "amount": amount_paise,
                        "currency": "USD",
                        "receipt": f"rcpt_{order_number}",
                        "notes": notes
                    })
                    rz_order_id = rz_order.get('id')
                except Exception as rz_err:
                    print(f"[RAZORPAY] Order creation error: {str(rz_err)}")
                    if IS_REAL_MODE:
                        raise Exception(f"Razorpay order creation failed: {str(rz_err)}")

            if not rz_order_id:
                if IS_REAL_MODE:
                    raise Exception("Unable to generate Razorpay Order ID.")
                rz_order_id = f"MOCK_ORD_{order_number}"

            db.execute(
                "UPDATE orders SET razorpay_order_id = ? WHERE id = ?",
                (rz_order_id, order_id)
            )
            db.commit()

            return jsonify({
                "success": True,
                "order_id": order_id,
                "order_number": order_number,
                "razorpay_order_id": rz_order_id,
                "razorpay_key_id": RAZORPAY_KEY_ID,
                "amount": int(final_total * 100),
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone
            })

    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": f"An error occurred: {str(e)}"}), 500
    finally:
        db.close()


@checkout_bp.route('/checkout/verify', methods=['POST'], endpoint='checkout_verify')
def checkout_verify():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized access."}), 401

    order_id = request.form.get('order_id')
    razorpay_payment_id = request.form.get('razorpay_payment_id', '').strip()
    razorpay_order_id = request.form.get('razorpay_order_id', '').strip()
    razorpay_signature = request.form.get('razorpay_signature', '').strip()
    is_mock = request.form.get('is_mock', 'false').lower() == 'true'

    if not order_id:
        return jsonify({"success": False, "message": "Missing order details."}), 400

    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, session['user_id'])).fetchone()
    if not order:
        db.close()
        return jsonify({"success": False, "message": "Order not found."}), 404

    if order['status'] != 'Pending Payment':
        db.close()
        return jsonify({"success": False, "message": "Order already processed."}), 400

    signature_valid = False
    if is_mock and not IS_REAL_MODE:
        signature_valid = True
    else:
        rz_client = get_razorpay_client()
        if rz_client:
            try:
                rz_client.utility.verify_payment_signature({
                    'razorpay_order_id': razorpay_order_id,
                    'razorpay_payment_id': razorpay_payment_id,
                    'razorpay_signature': razorpay_signature
                })
                signature_valid = True
            except Exception as e:
                print(f"[RAZORPAY] Signature verification failed: {str(e)}")

    if not signature_valid:
        db.close()
        return jsonify({"success": False, "message": "Payment verification failed. Invalid signature."}), 400

    try:
        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in order_items:
            product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (item['product_id'],)).fetchone()
            if not product or product['stocks'] < item['quantity']:
                db.close()
                return jsonify({"success": False, "message": f"Insufficient stock for {product['name'] if product else 'product'}."}), 400

        for item in order_items:
            db.execute("UPDATE products SET stocks = stocks - ? WHERE id = ?", (item['quantity'], item['product_id']))

        db.execute(
            """UPDATE orders 
               SET status = 'Processing', razorpay_payment_id = ?, razorpay_signature = ? 
               WHERE id = ?""",
            (razorpay_payment_id if (not is_mock or IS_REAL_MODE) else 'MOCK_PAY_' + razorpay_order_id, 
             razorpay_signature if (not is_mock or IS_REAL_MODE) else 'MOCK_SIG', 
             order_id)
        )

        if order['promo_code']:
            db.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",
                (order['promo_code'].upper(),)
            )

        db.commit()

        try:
            items_list = []
            for item in order_items:
                prod = db.execute("SELECT name FROM products WHERE id = ?", (item['product_id'],)).fetchone()
                items_list.append({
                    'product_name': prod['name'] if prod else 'Product',
                    'quantity': item['quantity'],
                    'price': item['price']
                })
            queue_order_confirmation_email(
                order['contact_email'],
                order['contact_name'],
                order['order_number'],
                order['total_amount'],
                f"{order['shipping_address']}, {order['city']}, {order['state']} – {order['zip_code']}",
                items_list
            )
        except Exception as mail_err:
            print(f"[MAIL ALERT ERROR] Failed to send order confirmation email: {str(mail_err)}")

        session['cart'] = {}
        session.modified = True
        db.close()

        flash(f"Payment successful! Order {order['order_number']} is now being processed. 🎉", "success")
        return jsonify({"success": True, "redirect_url": url_for('my_orders')})

    except Exception as e:
        db.rollback()
        db.close()
        return jsonify({"success": False, "message": f"Error updating order: {str(e)}"}), 500


@checkout_bp.route('/checkout/verify-paypal', methods=['POST'], endpoint='checkout_verify_paypal')
def checkout_verify_paypal():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized access."}), 401

    order_id = request.form.get('order_id')
    paypal_order_id = request.form.get('paypal_order_id', '').strip()
    is_mock = "MOCK_PAYPAL_ORD" in paypal_order_id or not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)

    if not order_id:
        return jsonify({"success": False, "message": "Missing order details."}), 400

    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, session['user_id'])).fetchone()

    if not order:
        db.close()
        return jsonify({"success": False, "message": "Order not found."}), 404

    if order['status'] != 'Pending Payment':
        db.close()
        return jsonify({"success": False, "message": "Order already processed."}), 400

    paypal_payment_id = None
    capture_success = False

    if is_mock:
        capture_success = True
        paypal_payment_id = f"MOCK_PAY_ID_{order['order_number']}"
    else:
        token = get_paypal_access_token()
        if token:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
                url = f"{get_paypal_api_base()}/v2/checkout/orders/{paypal_order_id}/capture"
                res = requests.post(url, headers=headers, timeout=10)
                if res.status_code in (200, 201):
                    res_data = res.json()
                    if res_data.get('status') == 'COMPLETED':
                        capture_success = True
                        try:
                            purchase_units = res_data.get('purchase_units', [])
                            payments = purchase_units[0].get('payments', {})
                            captures = payments.get('captures', [])
                            paypal_payment_id = captures[0].get('id')
                        except Exception:
                            paypal_payment_id = f"PAY_ID_{order['order_number']}"
                else:
                    print(f"[PAYPAL] Capture API failed: {res.status_code} - {res.text}")
            except Exception as e:
                print(f"[PAYPAL] Capture error: {str(e)}")

    if not capture_success:
        db.close()
        return jsonify({"success": False, "message": "PayPal payment capture failed."}), 400

    try:
        order_items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in order_items:
            product = db.execute("SELECT stocks, name FROM products WHERE id = ?", (item['product_id'],)).fetchone()
            if not product or product['stocks'] < item['quantity']:
                db.close()
                return jsonify({"success": False, "message": f"Insufficient stock for {product['name'] if product else 'product'}."}), 400

        for item in order_items:
            db.execute("UPDATE products SET stocks = stocks - ? WHERE id = ?", (item['quantity'], item['product_id']))

        db.execute(
            """UPDATE orders 
               SET status = 'Processing', paypal_payment_id = ? 
               WHERE id = ?""",
            (paypal_payment_id, order_id)
        )

        if order['promo_code']:
            db.execute(
                "UPDATE promo_codes SET used_count = used_count + 1 WHERE UPPER(code) = ?",
                (order['promo_code'].upper(),)
            )

        db.commit()

        try:
            items_list = []
            for item in order_items:
                prod = db.execute("SELECT name FROM products WHERE id = ?", (item['product_id'],)).fetchone()
                items_list.append({
                    'product_name': prod['name'] if prod else 'Product',
                    'quantity': item['quantity'],
                    'price': item['price']
                })
            queue_order_confirmation_email(
                order['contact_email'],
                order['contact_name'],
                order['order_number'],
                order['total_amount'],
                f"{order['shipping_address']}, {order['city']}, {order['state']} – {order['zip_code']}",
                items_list
            )
        except Exception as mail_err:
            print(f"[MAIL ALERT ERROR] Failed to send order confirmation email: {str(mail_err)}")

        session['cart'] = {}
        session.modified = True
        db.close()

        flash(f"Payment successful! Order {order['order_number']} is now being processed. 🎉", "success")
        return jsonify({"success": True, "redirect_url": url_for('my_orders')})

    except Exception as e:
        db.rollback()
        db.close()
        return jsonify({"success": False, "message": f"Error updating order: {str(e)}"}), 500
