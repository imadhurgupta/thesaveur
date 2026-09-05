def format_currency(value):
    """Format a number as currency (INR)."""
    try:
        val = float(value)
        return f"₹{val:,.2f}"
    except (ValueError, TypeError):
        return f"₹{value}"


def register_filters(app):
    """Register custom Jinja template filters."""
    app.jinja_env.filters['currency'] = format_currency
