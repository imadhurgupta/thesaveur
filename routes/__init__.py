from routes.storefront import storefront_bp
from routes.products import products_bp
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.password_reset import password_reset_bp
from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.orders import orders_bp
from routes.admin import register_admin_blueprints
from routes.api import register_api_blueprints

all_base_blueprints = [
    storefront_bp,
    products_bp,
    auth_bp,
    profile_bp,
    password_reset_bp,
    cart_bp,
    checkout_bp,
    orders_bp
]


def register_routes(app):
    """Register all customer storefront, auth, shopping, admin, and API blueprints."""
    for bp in all_base_blueprints:
        app.register_blueprint(bp)

    register_admin_blueprints(app)
    register_api_blueprints(app)
