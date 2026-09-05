import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from database import get_db
from services.cache_service import redis_client
from services.auth_service import allowed_file

products_bp = Blueprint('products', __name__)


@products_bp.route('/products', endpoint='products')
def products():
    category = request.args.get('category', 'all').strip()

    categories_list = None
    products_list = None

    if redis_client:
        try:
            cached_cats = redis_client.get("nav_categories_list")
            cached_prods = redis_client.get("all_products_list")
            if cached_cats:
                categories_list = json.loads(cached_cats.decode('utf-8'))
            if cached_prods:
                products_list = json.loads(cached_prods.decode('utf-8'))
        except Exception as e:
            print(f"[REDIS] Products cache read error: {e}")

    db = None
    if not categories_list or not products_list:
        db = get_db()

    if not categories_list:
        all_categories = db.execute(
            "SELECT * FROM categories ORDER BY display_order ASC"
        ).fetchall()
        categories_list = [dict(c) for c in all_categories]
        if redis_client:
            try:
                redis_client.setex("nav_categories_list", 3600, json.dumps(categories_list))
            except Exception as e:
                print(f"[REDIS] Categories list write error: {e}")

    if not products_list:
        all_products = db.execute(
            "SELECT * FROM products ORDER BY category, name"
        ).fetchall()
        products_list = [dict(p) for p in all_products]
        if redis_client:
            try:
                redis_client.setex("all_products_list", 3600, json.dumps(products_list))
            except Exception as e:
                print(f"[REDIS] Products list write error: {e}")

    if db:
        db.close()

    # Enrich products with sub-categories dynamically only if not set in the database
    for p in products_list:
        if p.get('sub_category') and p['sub_category'].strip() != '' and p['sub_category'].strip().lower() != 'other':
            continue
        name_lower = p['name'].lower()
        if 'green tea' in name_lower:
            p['sub_category'] = 'Green Tea'
        elif 'black tea' in name_lower or 'tea' in name_lower:
            p['sub_category'] = 'Black Tea'
        elif 'garam masala' in name_lower:
            p['sub_category'] = 'Blend Spices'
        elif 'powder' in name_lower or 'turmeric' in name_lower or 'chilli' in name_lower or 'pepper' in name_lower or 'aamchur' in name_lower:
            p['sub_category'] = 'Ground Spices'
        elif 't-shirt' in name_lower or 'shirt' in name_lower:
            p['sub_category'] = 'Apparel'
        elif 'bag' in name_lower or 'tote' in name_lower:
            p['sub_category'] = 'Accessories'
        else:
            p['sub_category'] = 'Other'

    return render_template(
        'products.html',
        products=products_list,
        categories=categories_list,
        active_filter=category
    )


@products_bp.route('/product/<id>', endpoint='product_detail')
def product_detail(id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()

    if not product:
        db.close()
        flash("Product not found.", "error")
        return redirect(url_for('products'))

    # Get all images for this product
    images = db.execute("SELECT image_filename FROM product_images WHERE product_id = ?", (id,)).fetchall()
    image_list = [img['image_filename'] for img in images]

    # Fallback if no images are stored
    if not image_list and product['image_filename']:
        image_list = [product['image_filename']]

    # Get related/similar products (strictly of the same category, limit 5)
    related_products = db.execute(
        "SELECT * FROM products WHERE category = ? AND id != ? LIMIT 5",
        (product['category'], id)
    ).fetchall()

    related_products_list = [dict(p) for p in related_products]

    # Fetch reviews for this product
    reviews = db.execute("SELECT * FROM reviews WHERE product_id = ? ORDER BY created_at DESC", (id,)).fetchall()
    reviews_list = [dict(r) for r in reviews]

    # Calculate review stats
    total_reviews = len(reviews_list)
    avg_rating = 0.0
    rating_breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}

    if total_reviews > 0:
        total_stars = sum(r['rating'] for r in reviews_list)
        avg_rating = round(total_stars / total_reviews, 1)
        for r in reviews_list:
            r_val = r['rating']
            if r_val in rating_breakdown:
                rating_breakdown[r_val] += 1

    # Check wishlist
    wishlist = session.get('wishlist', [])
    in_wishlist = str(id) in [str(w) for w in wishlist]

    product_dict = dict(product)
    specs = []
    if product_dict.get('specifications'):
        try:
            specs = json.loads(product_dict['specifications'])
        except Exception:
            pass

    db.close()
    return render_template(
        'product_detail.html', 
        product=product_dict, 
        images=image_list, 
        related_products=related_products_list,
        reviews=reviews_list,
        total_reviews=total_reviews,
        avg_rating=avg_rating,
        rating_breakdown=rating_breakdown,
        in_wishlist=in_wishlist,
        specs=specs
    )


@products_bp.route('/product/<id>/review', methods=['POST'], endpoint='add_review')
def add_review(id):
    if not session.get('user_id'):
        flash("You must be logged in to submit a review.", "error")
        return redirect(url_for('login', next=url_for('product_detail', id=id)))

    rating = request.form.get('rating')
    comment = request.form.get('comment', '').strip()
    user_name = session.get('user_name', 'Verified Buyer')

    if not rating:
        flash("Please select a star rating.", "error")
        return redirect(url_for('product_detail', id=id))

    try:
        rating_int = int(rating)
        if not (1 <= rating_int <= 5):
            raise ValueError()
    except ValueError:
        flash("Invalid rating value.", "error")
        return redirect(url_for('product_detail', id=id))

    db = get_db()

    # Handle review image upload (Max 15 MB)
    image_filename = None
    if 'review_image' in request.files:
        file = request.files['review_image']
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image format. Allowed formats: png, jpg, jpeg, gif, webp.", "error")
                return redirect(url_for('product_detail', id=id))
            
            # File size validation (Max 15 MB)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            
            if size > 15 * 1024 * 1024:
                flash("Image size exceeds the maximum limit of 15 MB.", "error")
                return redirect(url_for('product_detail', id=id))
                
            filename = secure_filename(file.filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/images')
            filepath = os.path.join(upload_folder, filename)
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(upload_folder, filename)
                counter += 1
            file.save(filepath)
            image_filename = filename

    db.execute(
        "INSERT INTO reviews (product_id, user_name, rating, comment, image_filename) VALUES (?, ?, ?, ?, ?)",
        (id, user_name, rating_int, comment, image_filename)
    )
    db.commit()
    db.close()

    flash("Thank you! Your review has been submitted successfully.", "success")
    return redirect(url_for('product_detail', id=id))
