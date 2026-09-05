"""
Business logic services and external integrations.
"""
from services.auth_service import admin_required, hash_password, generate_order_number, allowed_file, allowed_video_file
from services.cache_service import redis_client, invalidate_cache
from services.email_service import (
    send_custom_html_email, send_otp_email, send_login_alert_email,
    send_order_confirmation_email, send_order_shipped_email,
    send_order_delivered_email, send_order_status_update_email,
    queue_otp_email, queue_login_alert_email, queue_order_confirmation_email,
    queue_order_shipped_email, queue_order_delivered_email, queue_order_status_update_email
)
from services.razorpay_service import get_razorpay_client
from services.paypal_service import get_paypal_api_base, get_paypal_access_token
from services.shipping_calculator import compute_shipping_cost
from services.couriers_service import (
    generate_tracking_url, get_courier_metadata, get_courier_list,
    normalize_courier_code, COURIER_PARTNERS, get_custom_couriers_from_db
)
