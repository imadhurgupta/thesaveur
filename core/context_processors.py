import os
import json
from flask import session
from database import get_db
from core.config import PAYPAL_CLIENT_ID, PAYPAL_MODE
from services.cache_service import redis_client


def check_user_session():
    """Verify customer session against the database before each request."""
    user_id = session.get('user_id')
    if user_id:
        db = get_db()
        try:
            user = db.execute("SELECT id, full_name, is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                session['is_admin'] = bool(user['is_admin'])
                session['user_name'] = user['full_name']
            else:
                # Stale session cookie from deleted database, clear it
                session.clear()
        except Exception as e:
            print(f"[SESSION CHECK ERROR] {e}")
        finally:
            db.close()


def inject_paypal_config():
    """Inject PayPal client id and mode into templates."""
    return dict(
        paypal_client_id=PAYPAL_CLIENT_ID,
        paypal_mode=PAYPAL_MODE
    )


def inject_categories():
    """Inject categories and their subcategories for the navigation menu."""
    if redis_client:
        try:
            cached_val = redis_client.get("nav_categories")
            if cached_val:
                return dict(nav_categories=json.loads(cached_val.decode('utf-8')))
        except Exception as e:
            print(f"[REDIS] Read error in nav context: {e}")

    db = get_db()
    try:
        categories_raw = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        categories = []
        for cat in categories_raw:
            cat_dict = dict(cat)
            subcats = db.execute(
                "SELECT * FROM subcategories WHERE category_name = ? ORDER BY display_order ASC",
                (cat['name'],)
            ).fetchall()
            cat_dict['subcategories'] = [dict(sub) for sub in subcats]
            categories.append(cat_dict)

        if redis_client:
            try:
                redis_client.setex("nav_categories", 3600, json.dumps(categories))
            except Exception as e:
                print(f"[REDIS] Write error in nav context: {e}")

        return dict(nav_categories=categories)
    except Exception as e:
        print(f"[NAV CONTEXT] Error fetching categories: {e}")
        return dict(nav_categories=[])
    finally:
        db.close()


def inject_globals():
    """Inject global site details."""
    return {
        'site_name': os.environ.get('SITE_NAME', 'The Saveur'),
    }


def inject_global_data():
    """Inject global categories and subcategories for forms and dropdowns."""
    try:
        db = get_db()
        categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        subcategories = db.execute("SELECT * FROM subcategories ORDER BY category_name, display_order ASC").fetchall()
        db.close()
        return {'global_categories': categories, 'global_subcategories': subcategories}
    except Exception:
        return {'global_categories': [], 'global_subcategories': []}


def register_context_processors(app):
    """Register all context processors and before_request handlers on the Flask app."""
    app.before_request(check_user_session)
    app.context_processor(inject_paypal_config)
    app.context_processor(inject_categories)
    app.context_processor(inject_globals)
    app.context_processor(inject_global_data)
