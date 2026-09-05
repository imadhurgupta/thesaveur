from routes.api.webhooks import api_webhooks_bp
from routes.api.shipping import api_shipping_bp
from routes.api.media import api_media_bp

api_blueprints = [
    api_webhooks_bp,
    api_shipping_bp,
    api_media_bp
]


def register_api_blueprints(app):
    """Register all REST API blueprints."""
    for bp in api_blueprints:
        app.register_blueprint(bp)
