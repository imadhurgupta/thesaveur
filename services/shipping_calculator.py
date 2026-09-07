from database import get_db

def compute_shipping_cost(state_name, cart_dict):
    """
    Calculate location base shipping charge + product specific shipping charges.
    Returns: (location_charge, product_charge, total_shipping)
    All deliveries are Free.
    """
    return 0.0, 0.0, 0.0
