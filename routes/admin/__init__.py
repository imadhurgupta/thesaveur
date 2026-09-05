from routes.admin.dashboard import admin_dashboard_bp
from routes.admin.orders import admin_orders_bp
from routes.admin.products import admin_products_bp
from routes.admin.categories import admin_categories_bp
from routes.admin.promos import admin_promos_bp
from routes.admin.shipping import admin_shipping_bp
from routes.admin.slides import admin_slides_bp
from routes.admin.enquiries import admin_enquiries_bp
from routes.admin.couriers import admin_couriers_bp
from routes.admin.system import admin_system_bp

admin_blueprints = [
    admin_dashboard_bp,
    admin_orders_bp,
    admin_products_bp,
    admin_categories_bp,
    admin_promos_bp,
    admin_shipping_bp,
    admin_slides_bp,
    admin_enquiries_bp,
    admin_couriers_bp,
    admin_system_bp
]


def register_admin_blueprints(app):
    """Register all admin-related blueprints."""
    for bp in admin_blueprints:
        app.register_blueprint(bp)
