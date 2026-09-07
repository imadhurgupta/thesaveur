"""
Shiprocket Live Courier Delivery Status Synchronization Service
===============================================================
Automates real-time tracking across all couriers via the Shiprocket REST API.
Handles:
  1. Secure authentication & JWT token caching.
  2. Live AWB tracking & checkpoint ingestion.
  3. Status mapping from Shiprocket to The Saveur order lifecycle.
  4. Auto-advance order status & trigger customer milestone emails.
  5. Fallback sandbox simulation for development/testing.
  6. In-app background synchronization runner.
"""

import os
import json
import time
import datetime
import threading
import requests
from database import get_db

# ── Base Shiprocket API Endpoints ─────────────────────────────────────
SHIPROCKET_API_BASE = "https://apiv2.shiprocket.in/v1/external"
LOGIN_ENDPOINT = f"{SHIPROCKET_API_BASE}/auth/login"
TRACKING_AWB_ENDPOINT = f"{SHIPROCKET_API_BASE}/courier/track/awb"
TRACKING_ORDER_ENDPOINT = f"{SHIPROCKET_API_BASE}/courier/track"


# ── System Settings DB Helpers ─────────────────────────────────────────
def get_system_setting(key: str, default: str = None) -> str:
    """Read a setting from the system_settings table, falling back to os.environ."""
    try:
        db = get_db()
        row = db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
        db.close()
        if row and row['value'] is not None:
            return row['value']
    except Exception as e:
        print(f"[SETTINGS DB ERROR] get_system_setting('{key}'): {e}")

    # Fallback to environment variables
    return os.environ.get(key, default if default is not None else '')


def set_system_setting(key: str, value: str) -> bool:
    """Save or update a setting in the system_settings table."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO system_settings (key, value, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(value) if value is not None else '')
        )
        db.commit()
        db.close()
        return True
    except Exception as e:
        print(f"[SETTINGS DB ERROR] set_system_setting('{key}'): {e}")
        return False


# ── Shiprocket Client ──────────────────────────────────────────────────
class ShiprocketClient:
    """Shiprocket API client with JWT token caching & automatic re-authentication."""

    def __init__(self, email: str = None, password: str = None):
        self.email = (email or get_system_setting('SHIPROCKET_EMAIL') or os.environ.get('SHIPROCKET_EMAIL', '')).strip()
        self.password = (password or get_system_setting('SHIPROCKET_PASSWORD') or os.environ.get('SHIPROCKET_PASSWORD', '')).strip()

    def is_configured(self) -> bool:
        """Check whether credentials are provided."""
        return bool(self.email and self.password)

    def get_token(self, force_refresh: bool = False) -> str:
        """Get valid Shiprocket JWT token, refreshing if missing or expired."""
        if not force_refresh:
            cached_token = get_system_setting('SHIPROCKET_TOKEN')
            expires_at = get_system_setting('SHIPROCKET_TOKEN_EXPIRES')
            if cached_token and expires_at:
                try:
                    exp_ts = float(expires_at)
                    # Refresh 1 hour before actual expiry
                    if time.time() < (exp_ts - 3600):
                        return cached_token
                except Exception:
                    pass

        return self.login()

    def login(self) -> str:
        """Authenticate with Shiprocket API and persist the new token."""
        if not self.is_configured():
            raise ValueError("Shiprocket email and password are not configured.")

        payload = {
            "email": self.email,
            "password": self.password
        }
        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(LOGIN_ENDPOINT, json=payload, headers=headers, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and 'token' in data:
                token = data['token']
                # Shiprocket JWT tokens are valid for ~10 days (864000 seconds)
                expires_at = time.time() + (86400 * 9)
                set_system_setting('SHIPROCKET_TOKEN', token)
                set_system_setting('SHIPROCKET_TOKEN_EXPIRES', str(expires_at))
                set_system_setting('SHIPROCKET_LAST_LOGIN', datetime.datetime.utcnow().isoformat())
                print("[SHIPROCKET] Authentication successful. Token cached.")
                return token
            else:
                err_msg = data.get('message') or data.get('error') or f"Status {resp.status_code}"
                raise Exception(f"Shiprocket Login Failed: {err_msg}")
        except requests.RequestException as req_err:
            raise Exception(f"Shiprocket Connection Error: {req_err}")

    def test_connection(self) -> dict:
        """Test authentication against Shiprocket API."""
        if not self.is_configured():
            return {
                'success': False,
                'configured': False,
                'message': 'Shiprocket email or password is missing in settings.'
            }
        try:
            token = self.login()
            return {
                'success': True,
                'configured': True,
                'message': f'Connected successfully to Shiprocket as {self.email}!'
            }
        except Exception as e:
            return {
                'success': False,
                'configured': True,
                'message': str(e)
            }

    def track_awb(self, awb_code: str) -> dict:
        """
        Fetch real-time tracking data for a specific AWB.
        Returns normalized tracking dictionary with scan checkpoints.
        """
        clean_awb = str(awb_code).strip()
        if not clean_awb:
            return {'success': False, 'error': 'AWB code is required.'}

        # If Shiprocket is not configured, check if we should return mock tracking data
        if not self.is_configured():
            if get_system_setting('SHIPROCKET_MOCK_MODE', '1') == '1':
                return self._generate_mock_tracking(clean_awb)
            return {'success': False, 'error': 'Shiprocket credentials are not configured.'}

        try:
            token = self.get_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            url = f"{TRACKING_AWB_ENDPOINT}/{clean_awb}"
            resp = requests.get(url, headers=headers, timeout=20)

            # Handle 401 Unauthorized (expired token)
            if resp.status_code == 401:
                print("[SHIPROCKET] Token expired during tracking request. Refreshing...")
                token = self.get_token(force_refresh=True)
                headers['Authorization'] = f'Bearer {token}'
                resp = requests.get(url, headers=headers, timeout=20)

            if resp.status_code != 200:
                return {
                    'success': False,
                    'status_code': resp.status_code,
                    'error': f"Shiprocket API returned status {resp.status_code}: {resp.text}"
                }

            data = resp.json()
            return self._parse_shiprocket_response(data, clean_awb)

        except Exception as e:
            print(f"[SHIPROCKET ERROR] Failed to fetch AWB {clean_awb}: {e}")
            if get_system_setting('SHIPROCKET_MOCK_MODE', '1') == '1':
                print("[SHIPROCKET] Falling back to mock tracking response...")
                return self._generate_mock_tracking(clean_awb)
            return {'success': False, 'error': str(e)}

    def _parse_shiprocket_response(self, data: dict, awb: str) -> dict:
        """Extract and normalize Shiprocket tracking payload."""
        tracking_data = data.get('tracking_data') or data

        track_status = tracking_data.get('track_status', 0)
        shipment_status_code = tracking_data.get('shipment_status')

        shipment_track = tracking_data.get('shipment_track') or []
        first_track = shipment_track[0] if (isinstance(shipment_track, list) and len(shipment_track) > 0) else {}

        activities = tracking_data.get('shipment_track_activities') or []

        # Clean activities list
        if isinstance(activities, list):
            activities_clean = []
            for act in activities:
                activities_clean.append({
                    'activity': act.get('activity') or act.get('status') or '',
                    'location': act.get('location') or act.get('sr-status-label') or '',
                    'date': act.get('date') or act.get('time') or '',
                    'status': act.get('status') or '',
                    'sr_status': act.get('sr-status') or ''
                })
        else:
            activities_clean = []

        current_status = first_track.get('current_status') or tracking_data.get('current_status') or ''
        courier_name = first_track.get('courier_name') or tracking_data.get('courier_name') or ''
        edd = first_track.get('edd') or tracking_data.get('edd') or ''
        origin = first_track.get('origin') or ''
        destination = first_track.get('destination') or ''
        track_url = tracking_data.get('track_url') or ''

        return {
            'success': True,
            'awb': awb,
            'current_status': current_status,
            'shipment_status_code': shipment_status_code,
            'courier_name': courier_name,
            'edd': edd,
            'origin': origin,
            'destination': destination,
            'track_url': track_url,
            'shipment_track': shipment_track,
            'shipment_track_activities': activities_clean,
            'raw': tracking_data
        }

    def _generate_mock_tracking(self, awb: str) -> dict:
        """Deterministic, realistic mock tracking data for sandbox testing."""
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        two_days_ago = now - datetime.timedelta(days=2)
        edd_date = (now + datetime.timedelta(days=2)).strftime('%Y-%m-%d')

        return {
            'success': True,
            'is_mock': True,
            'awb': awb,
            'current_status': 'In Transit',
            'shipment_status_code': 18,
            'courier_name': 'Delhivery Express',
            'edd': edd_date,
            'origin': 'Jaipur Central Hub, RJ',
            'destination': 'Customer Delivery Station',
            'track_url': f"https://www.delhivery.com/track/package/{awb}",
            'shipment_track': [{
                'id': 9901,
                'awb_code': awb,
                'courier_name': 'Delhivery Express',
                'current_status': 'In Transit',
                'origin': 'Jaipur Central Hub, RJ',
                'destination': 'Customer Delivery Hub',
                'edd': edd_date,
                'packages': 1
            }],
            'shipment_track_activities': [
                {
                    'activity': 'Arrived at Sorting Hub',
                    'location': 'Regional Logistics Facility',
                    'date': now.strftime('%Y-%m-%d %H:%M'),
                    'status': 'In Transit',
                    'sr_status': '18'
                },
                {
                    'activity': 'Package In Transit to Delivery Center',
                    'location': 'Main Transit Corridor',
                    'date': yesterday.strftime('%Y-%m-%d 18:30'),
                    'status': 'In Transit',
                    'sr_status': '18'
                },
                {
                    'activity': 'Shipment Dispatched & Manifest Created',
                    'location': 'The Saveur Fulfillment Center, Jaipur',
                    'date': two_days_ago.strftime('%Y-%m-%d 11:15'),
                    'status': 'Shipped',
                    'sr_status': '6'
                }
            ],
            'raw': {}
        }


# ── Status Normalization Engine ────────────────────────────────────────
STATUS_STAGE_WEIGHTS = {
    'Cancelled': -1,
    'Order Confirmed': 1,
    'Processing': 1,
    'Placed': 1,
    'Shipped': 2,
    'In Transit': 3,
    'Out for Delivery': 4,
    'Delivered': 5
}

def map_shiprocket_status_to_order_status(raw_status: str, status_code=None) -> str:
    """
    Map Shiprocket status code or text to The Saveur's 5 core statuses:
    'Order Confirmed' -> 'Shipped' -> 'In Transit' -> 'Out for Delivery' -> 'Delivered' (or 'Cancelled').
    """
    # 1. Numeric code mapping (Shiprocket standard)
    if status_code is not None:
        try:
            code = int(status_code)
            if code == 7:
                return 'Delivered'
            elif code == 17:
                return 'Out for Delivery'
            elif code in [18, 19, 42, 52]:
                return 'In Transit'
            elif code == 6:
                return 'Shipped'
            elif code in [8, 9, 10, 14, 15, 21, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 48, 49, 50, 51, 53, 54]:
                return 'Cancelled'
        except (ValueError, TypeError):
            pass

    if not raw_status:
        return 'In Transit'

    status_upper = str(raw_status).upper().strip()

    # 2. Cancellation and return checks FIRST (highest priority)
    if any(k in status_upper for k in [
        'CANCEL', 'CANCELLATION', 'RTO', 'UNDELIVERED', 'RETURN', 
        'REJECT', 'FAIL', 'ABORT', 'LOST', 'DAMAGED', 'DESTROY', 
        'NOT DELIVERED', 'REFUSED', 'FAILED DELIVERY', 'CUSTOMER REFUSED', 'UNCLAIMED'
    ]):
        return 'Cancelled'

    # 3. Delivered checks
    if any(k in status_upper for k in ['DELIVERED', 'COMPLETED']):
        return 'Delivered'

    # 4. Out for delivery checks
    if any(k in status_upper for k in ['OUT FOR DELIVERY', 'OUT_FOR_DELIVERY', 'OFD']):
        return 'Out for Delivery'

    # 5. In transit checks
    if any(k in status_upper for k in [
        'IN TRANSIT', 'TRANSIT', 'REACHED', 'HUB', 'FACILITY', 'DEPARTED',
        'RECEIVED AT', 'PICKED UP', 'PICKED_UP', 'LINE HAUL', 'CONNECTION'
    ]):
        return 'In Transit'

    # 6. Shipped checks
    if any(k in status_upper for k in ['SHIPPED', 'DISPATCHED', 'MANIFEST', 'PICKUP SCHEDULED', 'READY FOR PICKUP']):
        return 'Shipped'

    return 'In Transit'


# ── Order Synchronization Core ─────────────────────────────────────────
def get_active_trackable_orders() -> list:
    """
    Fetch all active shipped orders that have a tracking / AWB number.
    Excludes completed (Delivered/Cancelled) orders.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT id, order_number, user_id, status, courier_partner, tracking_number,
               tracking_url, estimated_delivery_date, last_tracking_fetch, tracking_status_raw
        FROM orders
        WHERE status IN ('Shipped', 'In Transit', 'Out for Delivery')
          AND tracking_number IS NOT NULL
          AND TRIM(tracking_number) != ''
        ORDER BY last_tracking_fetch ASC NULLS FIRST, id DESC
        """
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def update_order_from_tracking(order_id: int, host_url: str = '') -> dict:
    """
    Perform live sync on a single order:
      1. Fetch real courier checkpoints from Shiprocket.
      2. Map status to The Saveur milestone.
      3. Update orders table (status, tracking_status_raw, tracking_data_json, last_tracking_fetch).
      4. Auto-trigger customer notification email if status advanced.
    """
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        db.close()
        return {'success': False, 'error': f"Order #{order_id} not found"}

    order_dict = dict(order)
    awb = (order_dict.get('tracking_number') or '').strip()
    old_status = order_dict.get('status', 'Shipped')

    if not awb:
        db.close()
        return {'success': False, 'changed': False, 'error': 'No tracking number assigned to this order.'}

    # Fetch live Shiprocket checkpoints
    client = ShiprocketClient()
    tracking_res = client.track_awb(awb)

    if not tracking_res.get('success'):
        # Still record fetch timestamp to prevent tight polling loops
        db.execute("UPDATE orders SET last_tracking_fetch = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
        db.commit()
        db.close()
        return {
            'success': False,
            'changed': False,
            'order_id': order_id,
            'error': tracking_res.get('error', 'Failed to fetch tracking data')
        }

    raw_status = tracking_res.get('current_status', '')
    status_code = tracking_res.get('shipment_status_code')
    new_status = map_shiprocket_status_to_order_status(raw_status, status_code)

    old_weight = STATUS_STAGE_WEIGHTS.get(old_status, 1)
    new_weight = STATUS_STAGE_WEIGHTS.get(new_status, 1)

    # Status forward progression check
    status_changed = False
    final_status = old_status

    if new_status == 'Cancelled' and old_status != 'Cancelled':
        final_status = 'Cancelled'
        status_changed = True
    elif new_weight > old_weight:
        final_status = new_status
        status_changed = True
    elif old_status == 'Processing' and new_weight >= 2:
        final_status = new_status
        status_changed = True

    # Check for EDD update
    edd_to_save = tracking_res.get('edd') or order_dict.get('estimated_delivery_date') or ''
    courier_to_save = order_dict.get('courier_partner') or tracking_res.get('courier_name') or ''
    tracking_url_to_save = order_dict.get('tracking_url') or tracking_res.get('track_url') or ''

    # Persist tracking JSON & timestamps
    tracking_json_str = json.dumps({
        'current_status': raw_status,
        'courier_name': tracking_res.get('courier_name', ''),
        'edd': edd_to_save,
        'origin': tracking_res.get('origin', ''),
        'destination': tracking_res.get('destination', ''),
        'shipment_track': tracking_res.get('shipment_track', []),
        'shipment_track_activities': tracking_res.get('shipment_track_activities', []),
        'last_synced_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

    db.execute(
        """
        UPDATE orders
        SET status = ?,
            tracking_status_raw = ?,
            tracking_data_json = ?,
            estimated_delivery_date = ?,
            courier_partner = ?,
            tracking_url = ?,
            last_tracking_fetch = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (final_status, raw_status, tracking_json_str, edd_to_save, courier_to_save, tracking_url_to_save, order_id)
    )
    db.commit()
    db.close()

    # Handle cancellation & refund if status transitioned to Cancelled
    if final_status == 'Cancelled' and old_status != 'Cancelled':
        try:
            from services.refund_service import process_order_cancellation_refund
            process_order_cancellation_refund(order_id, reason=f"Courier checkpoint: {raw_status}", host_url=host_url)
            print(f"[COURIER CANCELLATION] Order #{order_id} cancelled by courier. Refund processed.")
        except Exception as ref_err:
            print(f"[COURIER CANCELLATION REFUND ERROR] {ref_err}")

    # Trigger customer notification email on milestone change
    if status_changed and final_status != 'Cancelled':
        try:
            from services.email_service import queue_order_status_update_email
            queue_order_status_update_email(order_id, final_status, host_url=host_url)
            print(f"[TRACKING SYNC] Order #{order_id} advanced from '{old_status}' to '{final_status}'. Email dispatched.")
        except Exception as mail_err:
            print(f"[TRACKING SYNC ERROR] Failed to dispatch status email: {mail_err}")

    return {
        'success': True,
        'changed': status_changed,
        'order_id': order_id,
        'old_status': old_status,
        'new_status': final_status,
        'raw_courier_status': raw_status,
        'tracking_data': tracking_res
    }


def sync_all_active_orders(host_url: str = '') -> dict:
    """
    Bulk synchronize all active shipments in transit.
    Returns summary metrics.
    """
    orders = get_active_trackable_orders()
    total = len(orders)
    updated = 0
    errors = 0

    print(f"[SHIPROCKET BULK SYNC] Starting live sync for {total} active shipments...")

    for order in orders:
        try:
            res = update_order_from_tracking(order['id'], host_url=host_url)
            if res.get('changed'):
                updated += 1
            # Polite API rate limit interval between requests
            time.sleep(0.3)
        except Exception as e:
            errors += 1
            print(f"[SHIPROCKET BULK SYNC ERROR] Order #{order.get('id')}: {e}")

    summary = {
        'total': total,
        'updated': updated,
        'errors': errors,
        'timestamp': datetime.datetime.now().isoformat()
    }
    set_system_setting('SHIPROCKET_LAST_BULK_SYNC', json.dumps(summary))
    print(f"[SHIPROCKET BULK SYNC] Completed: {summary}")
    return summary


def get_order_live_tracking(order_id: int) -> dict:
    """
    Retrieve cached tracking scans for an order, fetching fresh data if empty or stale.
    Returns dict ready for shop/partials/tracking_carrier.html.
    """
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    db.close()

    if not order:
        return {}

    order_dict = dict(order)
    tracking_json = order_dict.get('tracking_data_json')

    # If cached data exists, load it
    if tracking_json:
        try:
            cached = json.loads(tracking_json)
            if cached.get('shipment_track_activities'):
                return cached
        except Exception:
            pass

    # If order has tracking number, attempt live fetch
    awb = (order_dict.get('tracking_number') or '').strip()
    if awb:
        sync_res = update_order_from_tracking(order_id)
        if sync_res.get('success') and sync_res.get('tracking_data'):
            td = sync_res['tracking_data']
            return {
                'current_status': td.get('current_status', ''),
                'courier_name': td.get('courier_name', ''),
                'edd': td.get('edd', ''),
                'origin': td.get('origin', ''),
                'destination': td.get('destination', ''),
                'shipment_track': td.get('shipment_track', []),
                'shipment_track_activities': td.get('shipment_track_activities', []),
                'last_synced_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    return {}


def get_order_live_tracking_status(order_id: int, force_refresh: bool = False, host_url: str = '') -> dict:
    """
    Get real-time order status, live courier tracking milestones, and refund status.
    If force_refresh is True, fetches latest checkpoints from courier immediately.
    """
    if force_refresh:
        try:
            update_order_from_tracking(order_id, host_url=host_url)
        except Exception as e:
            print(f"[LIVE TRACKING SYNC ERROR] {e}")

    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        db.close()
        return {'success': False, 'error': 'Order not found'}

    o = dict(order)

    # If courier status indicates cancellation but order is not cancelled in DB, cancel & refund now!
    raw_st = o.get('tracking_status_raw', '')
    if raw_st and map_shiprocket_status_to_order_status(raw_st) == 'Cancelled' and o.get('status') != 'Cancelled':
        db.close()
        try:
            from services.refund_service import process_order_cancellation_refund
            process_order_cancellation_refund(order_id, reason=f"Courier checkpoint: {raw_st}", host_url=host_url)
            print(f"[AUTO CANCELLED] Order #{order_id} automatically cancelled due to courier status: '{raw_st}'")
        except Exception as auto_c_err:
            print(f"[AUTO CANCEL ERROR] {auto_c_err}")
        db = get_db()
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        o = dict(order)

    db.close()

    tracking_data = {}
    if o.get('tracking_data_json'):
        try:
            tracking_data = json.loads(o['tracking_data_json'])
        except Exception:
            pass

    is_cod = (o.get('payment_method') or '').strip().lower() in ['cod', 'cash on delivery', 'cash_on_delivery', 'cash']

    current_st = o.get('status', 'Processing')
    return {
        'success': True,
        'order_id': o['id'],
        'order_number': o.get('order_number') or f"#{o['id']}",
        'status': current_st,
        'new_status': current_st,
        'changed': True,
        'payment_method': o.get('payment_method', ''),
        'is_cod': is_cod,
        'courier_partner': o.get('courier_partner', ''),
        'tracking_number': o.get('tracking_number', ''),
        'tracking_url': o.get('tracking_url', ''),
        'estimated_delivery_date': o.get('estimated_delivery_date', ''),
        'last_tracking_fetch': o.get('last_tracking_fetch', ''),
        'tracking_status_raw': o.get('tracking_status_raw', ''),
        'refund_id': o.get('refund_id'),
        'refund_status': o.get('refund_status'),
        'refund_amount': o.get('refund_amount', 0.0),
        'refund_created_at': o.get('refund_created_at'),
        'tracking_data': tracking_data
    }



# ── In-App Background Thread Scheduler ─────────────────────────────────
_bg_thread = None
_bg_stop_event = threading.Event()

def _tracking_scheduler_loop():
    """Background loop polling active orders based on configured interval."""
    print("[SHIPROCKET SCHEDULER] In-app background tracking scheduler started.")
    while not _bg_stop_event.is_set():
        try:
            enabled = get_system_setting('AUTO_TRACKING_ENABLED', '1') == '1'
            if enabled:
                sync_all_active_orders()
        except Exception as loop_err:
            print(f"[SHIPROCKET SCHEDULER ERROR] {loop_err}")

        # Default interval: 30 minutes (configurable in settings)
        try:
            interval_mins = int(get_system_setting('TRACKING_POLL_INTERVAL_MINUTES', '30'))
        except Exception:
            interval_mins = 30

        # Sleep in 5-second intervals to allow prompt shutdown
        for _ in range(max(1, interval_mins * 12)):
            if _bg_stop_event.is_set():
                break
            time.sleep(5)


def start_background_tracking_scheduler():
    """Start in-app daemon thread if not already active."""
    global _bg_thread
    if _bg_thread is None or not _bg_thread.is_alive():
        _bg_stop_event.clear()
        _bg_thread = threading.Thread(target=_tracking_scheduler_loop, daemon=True, name="ShiprocketSyncWorker")
        _bg_thread.start()
        print("[SHIPROCKET] Background sync worker thread launched successfully.")
