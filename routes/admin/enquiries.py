from flask import Blueprint, redirect, url_for, flash
from database import get_db
from services.auth_service import admin_required

admin_enquiries_bp = Blueprint('admin_enquiries_bp', __name__)


@admin_enquiries_bp.route('/admin/delete-enquiry/<int:id>', methods=['POST'], endpoint='admin_delete_enquiry')
@admin_required
def admin_delete_enquiry(id):
    db = get_db()
    db.execute("DELETE FROM enquiries WHERE id = ?", (id,))
    db.commit()
    db.close()
    flash('Enquiry deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@admin_enquiries_bp.route('/admin/enquiry/update-status/<int:id>/<string:status>', methods=['POST'], endpoint='admin_update_enquiry_status')
@admin_required
def admin_update_enquiry_status(id, status):
    if status not in ['Pending', 'Accepted', 'Declined']:
        flash("Invalid status update requested.", "error")
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    db.execute("UPDATE enquiries SET status = ? WHERE id = ?", (status, id))
    db.commit()
    db.close()
    flash(f"Proposal status updated to '{status}'.", "success")
    return redirect(url_for('admin_dashboard'))


@admin_enquiries_bp.route('/admin/resolve-enquiry/<int:id>', methods=['POST'], endpoint='admin_resolve_enquiry')
@admin_required
def admin_resolve_enquiry(id):
    db = get_db()
    enquiry = db.execute("SELECT status FROM enquiries WHERE id = ?", (id,)).fetchone()
    if enquiry:
        new_status = 'Resolved' if enquiry['status'] == 'Pending' else 'Pending'
        db.execute("UPDATE enquiries SET status = ? WHERE id = ?", (new_status, id))
        db.commit()
        flash(f'Enquiry status updated to {new_status}.', 'success')
    else:
        flash('Enquiry not found.', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))
