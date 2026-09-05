import os
from flask import Blueprint, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from database import get_db
from services.auth_service import admin_required, allowed_file

admin_slides_bp = Blueprint('admin_slides_bp', __name__)


@admin_slides_bp.route('/admin/add-slide', methods=['POST'], endpoint='admin_add_slide')
@admin_required
def admin_add_slide():
    badge_text = request.form.get('badge_text', '').strip()
    badge_icon = request.form.get('badge_icon', 'leaf').strip()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    button_text = request.form.get('button_text', 'Explore Products').strip()
    button_link = request.form.get('button_link', '/products').strip()
    slide_order = int(request.form.get('slide_order', 0) or 0)

    if not title:
        flash('Slide title is required.', 'error')
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
    db.execute(
        "INSERT INTO carousel_slides (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order)
    )
    db.commit()
    db.close()

    flash('Carousel slide added successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#carousel-tab')


@admin_slides_bp.route('/admin/edit-slide/<int:id>', methods=['POST'], endpoint='admin_edit_slide')
@admin_required
def admin_edit_slide(id):
    badge_text = request.form.get('badge_text', '').strip()
    badge_icon = request.form.get('badge_icon', 'leaf').strip()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    button_text = request.form.get('button_text', 'Explore Products').strip()
    button_link = request.form.get('button_link', '/products').strip()
    slide_order = int(request.form.get('slide_order', 0) or 0)

    if not title:
        flash('Slide title is required.', 'error')
        return redirect(url_for('admin_dashboard') + '#carousel-tab')

    db = get_db()
    slide = db.execute("SELECT image_filename FROM carousel_slides WHERE id = ?", (id,)).fetchone()
    if not slide:
        db.close()
        flash('Slide not found.', 'error')
        return redirect(url_for('admin_dashboard') + '#carousel-tab')

    image_filename = slide['image_filename']
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

    db.execute(
        """
        UPDATE carousel_slides 
        SET image_filename = ?, badge_icon = ?, badge_text = ?, title = ?, description = ?, button_text = ?, button_link = ?, slide_order = ?
        WHERE id = ?
        """,
        (image_filename, badge_icon, badge_text, title, description, button_text, button_link, slide_order, id)
    )
    db.commit()
    db.close()

    flash('Carousel slide updated successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#carousel-tab')


@admin_slides_bp.route('/admin/delete-slide/<int:id>', methods=['POST'], endpoint='admin_delete_slide')
@admin_required
def admin_delete_slide(id):
    db = get_db()
    db.execute("DELETE FROM carousel_slides WHERE id = ?", (id,))
    db.commit()
    db.close()
    flash('Carousel slide deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard') + '#carousel-tab')
