import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from database import get_db, generate_product_id
from services.auth_service import admin_required, allowed_file, allowed_video_file
from services.cache_service import invalidate_cache

admin_products_bp = Blueprint('admin_products_bp', __name__)


@admin_products_bp.route('/admin/add-product', methods=['GET', 'POST'], endpoint='admin_add_product')
@admin_required
def admin_add_product():
    if request.method == 'GET':
        db = get_db()
        categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        subcategories = db.execute(
            "SELECT s.*, c.display_name as parent_category_name FROM subcategories s JOIN categories c ON s.category_name = c.name ORDER BY s.category_name, s.display_order"
        ).fetchall()
        db.close()
        return render_template(
            'admin/add_product.html',
            categories=categories,
            subcategories=subcategories,
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "")
        )

    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    sub_category = request.form.get('sub_category', '').strip()
    description = request.form.get('description', '').strip()
    price = float(request.form.get('price', 0.0) or 0.0)
    stocks = int(request.form.get('stocks', 0) or 0)
    unit = request.form.get('unit', '100g').strip()
    is_bestseller = 1 if request.form.get('is_bestseller') else 0
    discount_percent = float(request.form.get('discount_percent', 0.0) or 0.0)
    shipping_charge = float(request.form.get('shipping_charge', 0.0) or 0.0)
    gst_rate = float(request.form.get('gst_rate', 0.0) or 0.0)

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    local_saved_files = []
    uploaded_files = request.files.getlist('local_images')
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/images')

    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(upload_folder, filename)
                counter += 1
            file.save(filepath)
            local_saved_files.append(filename)

    image_order_csv = request.form.get('image_order_csv', '').strip()
    image_list = []

    if image_order_csv:
        items = [item.strip() for item in image_order_csv.split(',') if item.strip()]
        for item in items:
            if item.startswith('local:'):
                try:
                    local_index = int(item.split(':')[1])
                    if 0 <= local_index < len(local_saved_files):
                        image_list.append(local_saved_files[local_index])
                except (ValueError, IndexError):
                    pass
            else:
                image_list.append(item)
    else:
        image_list.extend(local_saved_files)
        if not image_list:
            remote_images = request.form.get('remote_images', '').strip()
            manual_images = request.form.get('images', '').strip()
            combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
            if combined_csv:
                image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    primary_image = image_list[0] if image_list else ''

    video_url = ''
    video_file = request.files.get('video_file')
    if video_file and video_file.filename and allowed_video_file(video_file.filename):
        filename = secure_filename(video_file.filename)
        filepath = os.path.join(upload_folder, filename)
        base, extension = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{extension}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
        video_file.save(filepath)
        video_url = filename

    spec_keys = request.form.getlist('spec_keys[]')
    spec_values = request.form.getlist('spec_values[]')
    specs = []
    for k, v in zip(spec_keys, spec_values):
        k = k.strip()
        v = v.strip()
        if k and v:
            specs.append({'key': k, 'value': v})
    specifications_json = json.dumps(specs) if specs else None

    product_id = generate_product_id()

    db = get_db()
    db.execute(
        "INSERT INTO products (id, name, category, sub_category, description, image_filename, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate, video_url, specifications) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (product_id, name, category, sub_category, description, primary_image, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate, video_url, specifications_json)
    )

    if not image_list:
        db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, primary_image))
    else:
        for img in image_list:
            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (product_id, img))

    db.commit()
    invalidate_cache('all_products_list')
    db.close()

    flash(f'Product "{name}" added successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@admin_products_bp.route('/admin/edit-product/<id>', methods=['GET', 'POST'], endpoint='admin_edit_product')
@admin_required
def admin_edit_product(id):
    if request.method == 'GET':
        db = get_db()
        product_row = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
        if not product_row:
            flash('Product not found.', 'error')
            db.close()
            return redirect(url_for('admin_dashboard'))
        product = dict(product_row)
        specs = []
        if product.get('specifications'):
            try:
                specs = json.loads(product['specifications'])
            except Exception:
                pass
        product['specs'] = specs
        
        imgs = db.execute("SELECT image_filename FROM product_images WHERE product_id = ?", (id,)).fetchall()
        images_list = [img['image_filename'] for img in imgs]
        images_csv = ",".join(images_list)
        
        categories = db.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
        subcategories = db.execute(
            "SELECT s.*, c.display_name as parent_category_name FROM subcategories s JOIN categories c ON s.category_name = c.name ORDER BY s.category_name, s.display_order"
        ).fetchall()
        db.close()
        return render_template(
            'admin/edit_product.html',
            product=product,
            images_csv=images_csv,
            categories=categories,
            subcategories=subcategories,
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "")
        )

    name = request.form.get('name', '').strip()
    category = request.form.get('category', '').strip()
    sub_category = request.form.get('sub_category', '').strip()
    description = request.form.get('description', '').strip()
    price = float(request.form.get('price', 0.0) or 0.0)
    stocks = int(request.form.get('stocks', 0) or 0)
    unit = request.form.get('unit', '100g').strip()
    is_bestseller = 1 if request.form.get('is_bestseller') else 0
    discount_percent = float(request.form.get('discount_percent', 0.0) or 0.0)
    shipping_charge = float(request.form.get('shipping_charge', 0.0) or 0.0)
    gst_rate = float(request.form.get('gst_rate', 0.0) or 0.0)

    if not name or not category:
        flash('Product name and category are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    local_saved_files = []
    uploaded_files = request.files.getlist('local_images')
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/images')

    for file in uploaded_files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, filename)
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filename = f"{base}_{counter}{extension}"
                filepath = os.path.join(upload_folder, filename)
                counter += 1
            file.save(filepath)
            local_saved_files.append(filename)

    image_order_csv = request.form.get('image_order_csv', '').strip()
    image_list = []

    if image_order_csv:
        items = [item.strip() for item in image_order_csv.split(',') if item.strip()]
        for item in items:
            if item.startswith('local:'):
                try:
                    local_index = int(item.split(':')[1])
                    if 0 <= local_index < len(local_saved_files):
                        image_list.append(local_saved_files[local_index])
                except (ValueError, IndexError):
                    pass
            else:
                image_list.append(item)
    else:
        image_list.extend(local_saved_files)
        if not image_list:
            remote_images = request.form.get('remote_images', '').strip()
            manual_images = request.form.get('images', '').strip()
            combined_csv = f"{remote_images},{manual_images}" if remote_images and manual_images else (remote_images or manual_images)
            if combined_csv:
                image_list.extend([img.strip() for img in combined_csv.split(',') if img.strip()])

    db = get_db()
    existing_product = db.execute("SELECT video_url FROM products WHERE id = ?", (id,)).fetchone()
    video_url = existing_product['video_url'] if existing_product else ''

    if request.form.get('remove_video') == '1':
        video_url = ''

    video_file = request.files.get('video_file')
    if video_file and video_file.filename and allowed_video_file(video_file.filename):
        filename = secure_filename(video_file.filename)
        filepath = os.path.join(upload_folder, filename)
        base, extension = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{extension}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
        video_file.save(filepath)
        video_url = filename

    spec_keys = request.form.getlist('spec_keys[]')
    spec_values = request.form.getlist('spec_values[]')
    specs = []
    for k, v in zip(spec_keys, spec_values):
        k = k.strip()
        v = v.strip()
        if k and v:
            specs.append({'key': k, 'value': v})
    specifications_json = json.dumps(specs) if specs else None

    if image_list:
        primary_image = image_list[0]
        db.execute(
            "UPDATE products SET name = ?, category = ?, sub_category = ?, description = ?, image_filename = ?, price = ?, stocks = ?, unit = ?, is_bestseller = ?, discount_percent = ?, shipping_charge = ?, gst_rate = ?, video_url = ?, specifications = ? WHERE id = ?",
            (name, category, sub_category, description, primary_image, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate, video_url, specifications_json, id)
        )
        db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
        for img in image_list:
            db.execute("INSERT INTO product_images (product_id, image_filename) VALUES (?, ?)", (id, img))
    else:
        db.execute(
            "UPDATE products SET name = ?, category = ?, sub_category = ?, description = ?, price = ?, stocks = ?, unit = ?, is_bestseller = ?, discount_percent = ?, shipping_charge = ?, gst_rate = ?, video_url = ?, specifications = ? WHERE id = ?",
            (name, category, sub_category, description, price, stocks, unit, is_bestseller, discount_percent, shipping_charge, gst_rate, video_url, specifications_json, id)
        )

    db.commit()
    invalidate_cache('all_products_list')
    db.close()

    flash(f'Product "{name}" updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@admin_products_bp.route('/admin/delete-product/<id>', methods=['POST'], endpoint='admin_delete_product')
@admin_required
def admin_delete_product(id):
    db = get_db()
    product = db.execute("SELECT name FROM products WHERE id = ?", (id,)).fetchone()
    if product:
        try:
            db.execute("DELETE FROM order_items WHERE product_id = ?", (id,))
            db.execute("DELETE FROM products WHERE id = ?", (id,))
            db.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
            db.execute("DELETE FROM orders WHERE id NOT IN (SELECT DISTINCT order_id FROM order_items)")
            db.commit()
            invalidate_cache('all_products_list')
            flash(f'Product "{product["name"]}" deleted successfully.', 'success')
        except Exception as e:
            db.rollback()
            print(f"[DELETE PRODUCT] Error: {e}")
            flash(f'An error occurred while deleting product "{product["name"]}".', 'error')
    else:
        flash('Product not found.', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))


@admin_products_bp.route('/admin/bulk-delete-products', methods=['POST'], endpoint='admin_bulk_delete_products')
@admin_required
def admin_bulk_delete_products():
    product_ids = request.form.getlist('product_ids')
    if not product_ids:
        flash('No products selected for deletion.', 'error')
        return redirect(url_for('admin_dashboard') + '#products-tab')

    db = get_db()
    deleted_count = 0
    failed_products = []

    for pid in product_ids:
        product = db.execute("SELECT name FROM products WHERE id = ?", (pid,)).fetchone()
        if product:
            try:
                db.execute("DELETE FROM order_items WHERE product_id = ?", (pid,))
                db.execute("DELETE FROM products WHERE id = ?", (pid,))
                db.execute("DELETE FROM product_images WHERE product_id = ?", (pid,))
                db.commit()
                deleted_count += 1
            except Exception as e:
                db.rollback()
                print(f"[BULK DELETE] Error for product {pid}: {e}")
                failed_products.append(product['name'])

    try:
        db.execute("DELETE FROM orders WHERE id NOT IN (SELECT DISTINCT order_id FROM order_items)")
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[BULK DELETE] Error cleaning empty orders: {e}")

    invalidate_cache('all_products_list')
    db.close()

    if deleted_count > 0:
        if failed_products:
            flash(f'Successfully deleted {deleted_count} products. The following could not be deleted: {", ".join(failed_products)}', 'warning')
        else:
            flash(f'Successfully deleted {deleted_count} selected products.', 'success')
    else:
        if failed_products:
            flash(f'Could not delete the selected products: {", ".join(failed_products)}', 'error')
        else:
            flash('No products found or deleted.', 'error')

    return redirect(url_for('admin_dashboard') + '#products-tab')
