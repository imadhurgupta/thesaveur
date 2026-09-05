from flask import render_template

def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found_error(error):
        try:
            return render_template('404.html'), 404
        except Exception:
            return "Page not found (404)", 404

    @app.errorhandler(500)
    def internal_error(error):
        try:
            return render_template('500.html'), 500
        except Exception:
            return "Internal server error (500)", 500
