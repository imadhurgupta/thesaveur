import os
import random
from flask import Blueprint, request, redirect, url_for, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from database import get_db
from services.auth_service import admin_required, allowed_file
from services.tracking_service import get_system_setting, set_system_setting

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


@admin_slides_bp.route('/admin/shuffle-slides', methods=['POST'], endpoint='admin_shuffle_slides')
@admin_required
def admin_shuffle_slides():
    """Randomly shuffle the slide_order of all carousel slides in database."""
    db = get_db()
    slides = db.execute("SELECT id FROM carousel_slides ORDER BY id ASC").fetchall()
    if not slides:
        db.close()
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'No carousel slides found to shuffle.'}), 400
        flash('No carousel slides found to shuffle.', 'warning')
        return redirect(url_for('admin_dashboard') + '#carousel-tab')

    slide_ids = [s['id'] for s in slides]
    random_orders = list(range(1, len(slide_ids) + 1))
    random.shuffle(random_orders)

    for slide_id, new_order in zip(slide_ids, random_orders):
        db.execute("UPDATE carousel_slides SET slide_order = ? WHERE id = ?", (new_order, slide_id))
    db.commit()
    db.close()

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': f'All {len(slide_ids)} carousel slides shuffled successfully!',
            'count': len(slide_ids)
        }), 200

    flash(f'All {len(slide_ids)} carousel slides shuffled successfully!', 'success')
    return redirect(url_for('admin_dashboard') + '#carousel-tab')


@admin_slides_bp.route('/admin/toggle-carousel-shuffle', methods=['POST'], endpoint='admin_toggle_carousel_shuffle')
@admin_required
def admin_toggle_carousel_shuffle():
    """Toggle dynamic random shuffling of carousel slides on the storefront."""
    data = request.get_json(silent=True) or request.form or {}
    current_setting = get_system_setting('carousel_shuffle_storefront', 'false')

    if 'enabled' in data:
        new_val_str = 'true' if str(data['enabled']).lower() in ('true', '1', 'yes') else 'false'
    else:
        new_val_str = 'false' if current_setting == 'true' else 'true'

    set_system_setting('carousel_shuffle_storefront', new_val_str)

    is_enabled = (new_val_str == 'true')
    msg = 'Storefront dynamic slide auto-shuffle enabled!' if is_enabled else 'Storefront slide auto-shuffle disabled.'

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'enabled': is_enabled,
            'message': msg
        }), 200

    flash(msg, 'success')
    return redirect(url_for('admin_dashboard') + '#carousel-tab')
