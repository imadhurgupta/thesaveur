from datetime import datetime
from flask import Blueprint, request, jsonify, session
from database import get_db
from services.auth_service import admin_required
from services.shipping_calculator import compute_shipping_cost

api_shipping_bp = Blueprint('api_shipping_bp', __name__)


@api_shipping_bp.route('/api/calculate-shipping', methods=['POST', 'GET'], endpoint='calculate_shipping')
def calculate_shipping():
    """AJAX endpoint: calculate shipping charges - delivery is completely free for all orders."""
    return jsonify({
        'success': True,
        'location_charge': 0.0,
        'product_charge': 0.0,
        'shipping_charge': 0.0,
        'total_shipping': 0.0,
        'message': "Free Delivery on all orders"
    })


@api_shipping_bp.route('/api/validate-promo', methods=['POST'], endpoint='validate_promo')
def validate_promo():
    """AJAX endpoint: validate a promo code against the current cart subtotal."""
    if 'user_id' not in session:
        return jsonify({'valid': False, 'message': 'Please log in first.'})

    data = request.get_json() or {}
    code = data.get('code', '').strip().upper()
    subtotal = float(data.get('subtotal', 0))

    if not code:
        return jsonify({'valid': False, 'message': 'Enter a promo code.'})

    db = get_db()
    promo = db.execute(
        "SELECT * FROM promo_codes WHERE UPPER(code) = ? AND is_active = 1",
        (code,)
    ).fetchone()
    db.close()

    if not promo:
        return jsonify({'valid': False, 'message': 'Invalid or inactive promo code.'})

    if promo['expires_at']:
        try:
            exp = datetime.fromisoformat(promo['expires_at'])
            if datetime.now() > exp:
                return jsonify({'valid': False, 'message': 'This promo code has expired.'})
        except Exception:
            pass

    if promo['max_uses'] > 0 and promo['used_count'] >= promo['max_uses']:
        return jsonify({'valid': False, 'message': 'This promo code has reached its usage limit.'})

    if subtotal < promo['min_order_amount']:
        return jsonify({
            'valid': False,
            'message': f"Minimum order ${promo['min_order_amount']:.0f} required for this code."
        })

    if promo['discount_type'] == 'percent':
        discount_amount = round(subtotal * promo['discount_value'] / 100, 2)
    else:
        discount_amount = min(round(promo['discount_value'], 2), subtotal)

    final_total = round(subtotal - discount_amount, 2)

    return jsonify({
        'valid': True,
        'code': promo['code'],
        'discount_type': promo['discount_type'],
        'discount_value': promo['discount_value'],
        'discount_amount': discount_amount,
        'final_total': final_total,
        'message': f"Code applied! You save ${discount_amount:.2f}"
    })
