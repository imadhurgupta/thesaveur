import os
import sqlite3
from flask import Blueprint, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from database import get_db
from services.auth_service import admin_required, allowed_file
from services.cache_service import invalidate_cache

admin_categories_bp = Blueprint('admin_categories_bp', __name__)


@admin_categories_bp.route('/admin/add-category', methods=['POST'], endpoint='admin_add_category')
@admin_required
def admin_add_category():
    name = request.form.get('name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    description = request.form.get('description', '').strip()
    display_order = int(request.form.get('display_order', 0) or 0)

    if not name or not display_name:
        flash('Category name and display name are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    uploaded_file = request.files.get('local_images')
    remote_image = request.form.get('remote_images', '').strip()
    image_filename = ''
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/images')

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):
        filename = secure_filename(uploaded_file.filename)
        filepath = os.path.join(upload_folder, filename)
        base, extension = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{extension}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
        uploaded_file.save(filepath)
        image_filename = filename
    elif remote_image:
        image_filename = remote_image

    db = get_db()
    try:
        db.execute(
            "INSERT INTO categories (name, display_name, description, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
            (name, display_name, description, image_filename, display_order)
        )
        db.commit()
        invalidate_cache('nav_categories', 'nav_categories_list')
        flash(f'Category "{display_name}" added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Category name "{name}" already exists.', 'error')
    db.close()

    return redirect(url_for('admin_dashboard'))


@admin_categories_bp.route('/admin/edit-category/<int:id>', methods=['POST'], endpoint='admin_edit_category')
@admin_required
def admin_edit_category(id):
    name = request.form.get('name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    description = request.form.get('description', '').strip()
    display_order = int(request.form.get('display_order', 0) or 0)

    if not name or not display_name:
        flash('Category name and display name are required.', 'error')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    category = db.execute("SELECT name, image_filename FROM categories WHERE id = ?", (id,)).fetchone()
    if not category:
        db.close()
        flash('Category not found.', 'error')
        return redirect(url_for('admin_dashboard'))

    image_filename = category['image_filename']
    uploaded_file = request.files.get('local_images')
    remote_image = request.form.get('remote_images', '').strip()
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'static/images')

    if uploaded_file and uploaded_file.filename and allowed_file(uploaded_file.filename):
        filename = secure_filename(uploaded_file.filename)
        filepath = os.path.join(upload_folder, filename)
        base, extension = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{extension}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
        uploaded_file.save(filepath)
        image_filename = filename
    elif remote_image:
        image_filename = remote_image

    old_name = category['name']
    db.execute(
        """
        UPDATE categories 
        SET name = ?, display_name = ?, description = ?, image_filename = ?, display_order = ?
        WHERE id = ?
        """,
        (name, display_name, description, image_filename, display_order, id)
    )

    if old_name != name:
        db.execute("UPDATE subcategories SET category_name = ? WHERE category_name = ?", (name, old_name))
        db.execute("UPDATE products SET category = ? WHERE category = ?", (name, old_name))

    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()

    flash(f'Category "{display_name}" updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@admin_categories_bp.route('/admin/delete-category/<int:id>', methods=['POST'], endpoint='admin_delete_category')
@admin_required
def admin_delete_category(id):
    db = get_db()
    db.execute("DELETE FROM categories WHERE id = ?", (id,))
    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()
    flash('Category deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@admin_categories_bp.route('/admin/add-subcategory', methods=['POST'], endpoint='admin_add_subcategory')
@admin_required
def admin_add_subcategory():
    category_name = request.form.get('category_name', '').strip()
    name = request.form.get('name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    description = request.form.get('description', '').strip()
    display_order = int(request.form.get('display_order', 0) or 0)

    if not category_name or not name or not display_name:
        flash('Parent category, subcategory name, and display name are required.', 'error')
        return redirect(url_for('admin_dashboard') + '#categories-tab')

    db = get_db()
    try:
        db.execute(
            "INSERT INTO subcategories (category_name, name, display_name, description, display_order) VALUES (?, ?, ?, ?, ?)",
            (category_name, name, display_name, description, display_order)
        )
        db.commit()
        invalidate_cache('nav_categories', 'nav_categories_list')
        flash(f'Subcategory "{display_name}" added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Subcategory name "{name}" already exists.', 'error')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard') + '#categories-tab')


@admin_categories_bp.route('/admin/delete-subcategory/<int:id>', methods=['POST'], endpoint='admin_delete_subcategory')
@admin_required
def admin_delete_subcategory(id):
    db = get_db()
    db.execute("DELETE FROM subcategories WHERE id = ?", (id,))
    db.commit()
    invalidate_cache('nav_categories', 'nav_categories_list')
    db.close()
    flash('Subcategory deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#categories-tab')
