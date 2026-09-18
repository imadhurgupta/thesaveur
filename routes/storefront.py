from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from database import get_db

storefront_bp = Blueprint('storefront', __name__)


@storefront_bp.route('/', endpoint='home')
def home():
    db = get_db()
    bestsellers_raw = db.execute(
        "SELECT * FROM products WHERE is_bestseller = 1 LIMIT 10"
    ).fetchall()

    bestsellers = []
    for p in bestsellers_raw:
        p_dict = dict(p)
        stats = db.execute("""
            SELECT COUNT(*) AS count, AVG(rating) AS avg
            FROM reviews
            WHERE product_id = ?
        """, (p['id'],)).fetchone()
        p_dict['review_count'] = stats['count'] if stats else 0
        p_dict['avg_rating'] = round(stats['avg'], 1) if stats and stats['avg'] else 0.0
        bestsellers.append(p_dict)

    carousel_slides = db.execute(
        "SELECT * FROM carousel_slides ORDER BY slide_order ASC"
    ).fetchall()
    categories = db.execute(
        "SELECT * FROM categories ORDER BY display_order ASC"
    ).fetchall()

    # Fetch per-product review stats for the homepage snapshot
    product_reviews = db.execute("""
        SELECT p.id, p.name, p.category, p.image_filename,
               COUNT(r.id) AS review_count,
               ROUND(CAST(AVG(r.rating) AS NUMERIC), 1) AS avg_rating
        FROM products p
        INNER JOIN reviews r ON r.product_id = p.id
        GROUP BY p.id, p.name, p.category, p.image_filename
        HAVING COUNT(r.id) > 0
        ORDER BY ROUND(CAST(AVG(r.rating) AS NUMERIC), 1) DESC, COUNT(r.id) DESC
        LIMIT 8
    """).fetchall()

    # Site-wide aggregate: Set customer review rating at 5.0 with a base of 100+ reviews
    reviews_count_row = db.execute("SELECT COUNT(*) FROM reviews").fetchone()
    db_reviews_count = reviews_count_row[0] if reviews_count_row else 0
    
    site_stats = {
        'total_reviews': 100 + db_reviews_count,
        'overall_rating': 5.0
    }

    # Site-wide orders statistics
    db_orders_count = db.execute("SELECT COUNT(*) FROM orders WHERE status != 'Pending Payment' AND status != 'Cancelled'").fetchone()[0]
    total_delivered_count = 8000 + db_orders_count

    # States served: base count of 28 states + distinct states from orders
    db_states_count = db.execute("SELECT COUNT(DISTINCT state) FROM orders WHERE state IS NOT NULL AND state != ''").fetchone()[0]
    states_served = max(28, db_states_count)

    # Subscribers/Users count: 5000 base + real registered users + newsletter subscribers
    db_user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    db_subs_count = db.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
    subscriber_count = 5000 + db_user_count + db_subs_count

    db.close()
    return render_template(
        'index.html',
        bestsellers=bestsellers,
        carousel_slides=carousel_slides,
        categories=categories,
        product_reviews=product_reviews,
        site_stats=site_stats,
        total_delivered_count=total_delivered_count,
        states_served=states_served,
        subscriber_count=subscriber_count
    )


@storefront_bp.route('/about', endpoint='about')
def about():
    return render_template('about.html')


@storefront_bp.route('/contact', endpoint='contact')
def contact():
    return render_template('contact.html')


@storefront_bp.route('/sitemap.xml', endpoint='sitemap')
def sitemap():
    try:
        pages = []
        host_url = request.host_url.rstrip('/')
        today = datetime.utcnow().strftime('%Y-%m-%d')

        # ── 1. Core static pages ────────────────────────────────
        static_pages = [
            ('/',             'daily',   '1.0'),
            ('/products',     'daily',   '0.9'),
            ('/about',        'monthly', '0.7'),
            ('/contact',      'monthly', '0.7'),
            ('/track-order',  'weekly',  '0.6'),
        ]
        for url, freq, priority in static_pages:
            pages.append({
                'loc':        f"{host_url}{url}",
                'lastmod':    today,
                'changefreq': freq,
                'priority':   priority
            })

        db = get_db()

        # ── 2. Category filter pages ────────────────────────────
        categories = db.execute(
            "SELECT name FROM categories ORDER BY display_order ASC"
        ).fetchall()
        for cat in categories:
            try:
                cat_name = cat['name']
            except (KeyError, TypeError):
                cat_name = cat[0]
            pages.append({
                'loc':        f"{host_url}/products?category={cat_name.lower()}",
                'lastmod':    today,
                'changefreq': 'weekly',
                'priority':   '0.8'
            })

        # ── 3. Individual product pages ─────────────────────────
        products_rows = db.execute(
            "SELECT id, updated_at FROM products"
        ).fetchall()
        db.close()

        for prod in products_rows:
            try:
                pid      = prod['id']
                lastmod  = (prod['updated_at'] or today)[:10]
            except (KeyError, TypeError):
                pid     = prod[0]
                lastmod = today
            pages.append({
                'loc':        f"{host_url}/product/{pid}",
                'lastmod':    lastmod,
                'changefreq': 'weekly',
                'priority':   '0.7'
            })

        # ── Build XML ───────────────────────────────────────────
        xml  = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        xml += '        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        xml += '        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9\n'
        xml += '        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">\n'
        for page in pages:
            xml += '  <url>\n'
            xml += f"    <loc>{page['loc']}</loc>\n"
            xml += f"    <lastmod>{page['lastmod']}</lastmod>\n"
            xml += f"    <changefreq>{page['changefreq']}</changefreq>\n"
            xml += f"    <priority>{page['priority']}</priority>\n"
            xml += '  </url>\n'
        xml += '</urlset>\n'

        return Response(xml, mimetype='application/xml')
    except Exception as e:
        print(f"[SITEMAP ERROR] {e}")
        return "Internal Server Error", 500


@storefront_bp.route('/robots.txt', endpoint='robots')
def robots():
    host_url = request.host_url.rstrip('/')
    content = "User-agent: *\n"
    content += "Allow: /\n"
    content += "Disallow: /admin/\n"
    content += "Disallow: /checkout/submit\n"
    content += "Disallow: /checkout/verify\n\n"
    content += f"Sitemap: {host_url}/sitemap.xml\n"
    return Response(content, mimetype='text/plain')


@storefront_bp.route('/submit-enquiry', methods=['POST'], endpoint='submit_enquiry')
def submit_enquiry():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    product_interest = request.form.get('product_interest', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email:
        flash('Name and email are required.', 'error')
        return redirect(request.referrer or url_for('contact'))

    db = get_db()
    db.execute(
        "INSERT INTO enquiries (name, email, phone, product_interest, message) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, product_interest, message)
    )
    db.commit()
    db.close()

    flash('Thank you! Your enquiry has been received. We\'ll get back to you within 24 hours.', 'success')
    return redirect(request.referrer or url_for('contact'))


@storefront_bp.route('/submit-proposal', methods=['POST'], endpoint='submit_proposal')
def submit_proposal():
    product_id = request.form.get('product_id', '').strip()
    product_name = request.form.get('product_name', '').strip()
    proposed_price = request.form.get('proposed_price', '').strip()
    proposed_qty = request.form.get('proposed_qty', '').strip()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not proposed_price or not proposed_qty:
        flash('Required fields are missing.', 'error')
        return redirect(request.referrer or url_for('home'))

    try:
        deal_value = float(proposed_price) * float(proposed_qty)
    except ValueError:
        deal_value = 0.0

    full_message = (
        f"💵 PROPOSED DEAL\n"
        f"Proposed Price: ${proposed_price} per unit\n"
        f"Proposed Quantity: {proposed_qty} units\n"
        f"Total Deal Value: ${deal_value:.2f}\n\n"
        f"Client Note:\n{message}"
    )
    product_interest = f"{product_name} (ID: {product_id}) [Deal Proposal]"

    db = get_db()
    db.execute(
        "INSERT INTO enquiries (name, email, phone, product_interest, message) VALUES (?, ?, ?, ?, ?)",
        (name, email, phone, product_interest, full_message)
    )
    db.commit()
    db.close()

    flash(f"Proposal submitted! We will review your offer of ${proposed_price} for {proposed_qty} units and contact you soon.", "success")
    return redirect(request.referrer or url_for('home'))


@storefront_bp.route('/newsletter/subscribe', methods=['POST'], endpoint='newsletter_subscribe')
def newsletter_subscribe():
    email = request.form.get('email', '').strip()
    if not email:
        return jsonify({'status': 'error', 'message': 'Email address is required.'}), 400
        
    db = get_db()
    try:
        existing = db.execute("SELECT id FROM subscribers WHERE email = ?", (email,)).fetchone()
        if existing:
            db_user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            db_subs_count = db.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
            total = 5000 + db_user_count + db_subs_count
            db.close()
            return jsonify({'status': 'success', 'message': 'You are already subscribed!', 'count': total})
            
        db.execute("INSERT INTO subscribers (email) VALUES (?)", (email,))
        db.commit()
        
        db_user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        db_subs_count = db.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        total = 5000 + db_user_count + db_subs_count
        db.close()
        return jsonify({'status': 'success', 'message': 'Thank you for subscribing!', 'count': total})
    except Exception as e:
        db.close()
        return jsonify({'status': 'error', 'message': f'Subscription failed: {str(e)}'}), 500
