from database import get_db

def compute_shipping_cost(state_name, cart_dict):
    """
    Calculate location base shipping charge + product specific shipping charges.
    Returns: (location_charge, product_charge, total_shipping)
    """
    db = get_db()
    try:
        state_row = db.execute(
            "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = ?",
            (state_name.strip().upper(),)
        ).fetchone()

        if state_row:
            location_charge = float(state_row['charge'])
        else:
            default_row = db.execute(
                "SELECT charge FROM location_shipping_charges WHERE UPPER(state) = 'DEFAULT'"
            ).fetchone()
            location_charge = float(default_row['charge']) if default_row else 60.0

        product_charge = 0.0
        if cart_dict:
            product_ids = [int(pid) for pid in cart_dict.keys() if str(pid).isdigit()]
            if product_ids:
                placeholders = ','.join('?' for _ in product_ids)
                products_rows = db.execute(
                    f"SELECT id, shipping_charge FROM products WHERE id IN ({placeholders})",
                    product_ids
                ).fetchall()

                prod_charge_map = {row['id']: float(row['shipping_charge'] or 0.0) for row in products_rows}
                for pid, qty in cart_dict.items():
                    if str(pid).isdigit() and int(pid) in prod_charge_map:
                        product_charge += prod_charge_map[int(pid)] * int(qty)

        total_shipping = location_charge + product_charge
        return location_charge, product_charge, total_shipping
    finally:
        db.close()
