import os
import jinja2
from flask import Flask, url_for
from core.config import SECRET_KEY, SESSION_COOKIE_NAME, UPLOAD_FOLDER
from core.context_processors import register_context_processors
from core.filters import register_filters
from core.error_handlers import register_error_handlers
from routes import register_routes
from database import init_db


def configure_endpoint_aliases(app):
    """
    Ensure 100% backward compatibility for all templates and redirects using un-namespaced url_for:
    e.g. url_for('home') -> url_for('storefront.home')
         url_for('login') -> url_for('auth.login')
         url_for('admin_dashboard') -> url_for('admin_dashboard_bp.admin_dashboard')
    """
    endpoint_map = {}
    for rule in app.url_map.iter_rules():
        if '.' in rule.endpoint:
            short_name = rule.endpoint.split('.', 1)[1]
            if short_name not in endpoint_map:
                endpoint_map[short_name] = rule.endpoint

    def alias_url_build_error_handler(error, endpoint, values):
        target = endpoint_map.get(endpoint)
        if target:
            return url_for(target, **values)
        return None

    app.url_build_error_handlers.append(alias_url_build_error_handler)


def create_app():
    """Application factory for The Saveur Flask web application."""
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.config['SESSION_COOKIE_NAME'] = SESSION_COOKIE_NAME
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # Configure multi-directory Jinja template loader for modular template subfolders
    template_dirs = [
        os.path.join(app.root_path, 'templates'),
        os.path.join(app.root_path, 'templates', 'layouts'),
        os.path.join(app.root_path, 'templates', 'storefront'),
        os.path.join(app.root_path, 'templates', 'products'),
        os.path.join(app.root_path, 'templates', 'auth'),
        os.path.join(app.root_path, 'templates', 'shop'),
        os.path.join(app.root_path, 'templates', 'admin'),
    ]
    app.jinja_loader = jinja2.FileSystemLoader(template_dirs)

    # Initialize SQLite database schema
    with app.app_context():
        init_db()

    # Register template filters, context processors & error handlers
    register_filters(app)
    register_context_processors(app)
    register_error_handlers(app)

    # Register modular route blueprints
    register_routes(app)

    # Enable seamless endpoint aliasing for all Jinja2 templates
    configure_endpoint_aliases(app)

    return app


# Main application instance for WSGI / direct execution
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
