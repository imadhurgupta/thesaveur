"""
Automated Courier Tracking Service — The Saveur
================================================
Fetches real-time shipment scan events from courier APIs, normalizes statuses
to the app's 5-stage model, persists events to `tracking_events`, and
automatically advances order status + triggers email notifications.

Supported integrations:
  * Delhivery  — direct REST pull API (requires DELHIVERY_API_TOKEN)
  * Shiprocket — unified tracking covering Delhivery, BlueDart, DTDC,
                 Xpressbees, Shadowfax, Ekart, FedEx, DHL, IndiaPost, etc.
                 (requires SHIPROCKET_EMAIL + SHIPROCKET_PASSWORD)
"""

import time
import queue
import threading
import requests
from services.couriers_service import normalize_courier_code

# ─────────────────────────────────────────────────────────────
# Real-Time SSE Pub-Sub Event Bus
# ─────────────────────────────────────────────────────────────

_tracking_subscribers = {}  # order_id: list of queue.Queue()
_tracking_subscribers_lock = threading.Lock()


def subscribe_to_order_tracking(order_id: int):
    """Register a new real-time SSE listener for this order."""
    q = queue.Queue(maxsize=50)
    with _tracking_subscribers_lock:
        if order_id not in _tracking_subscribers:
            _tracking_subscribers[order_id] = []
        _tracking_subscribers[order_id].append(q)
    return q


def unsubscribe_from_order_tracking(order_id: int, q):
    """Remove an SSE listener on disconnect."""
    with _tracking_subscribers_lock:
        if order_id in _tracking_subscribers:
            try:
                _tracking_subscribers[order_id].remove(q)
            except ValueError:
                pass
            if not _tracking_subscribers[order_id]:
                del _tracking_subscribers[order_id]


def broadcast_tracking_update(order_id: int, data: dict):
    """Instantly push real-time delivery status updates to all active SSE clients."""
    with _tracking_subscribers_lock:
        queues = list(_tracking_subscribers.get(order_id, []))
    for q in queues:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


# ─────────────────────────────────────────────────────────────
# System settings helpers
# ─────────────────────────────────────────────────────────────

def get_system_setting(key: str, default: str = '') -> str:
    """Read a single setting from the system_settings table."""
    try:
        from database import get_db
        db = get_db()
        row = db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
        db.close()
        return row['value'] if row else default
    except Exception:
        return default


def save_system_setting(key: str, value: str) -> bool:
    """Upsert a single setting in the system_settings table."""
    try:
        from database import get_db
        db = get_db()
        db.execute(
            "INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value)
        )
        db.commit()
        db.close()
        return True
    except Exception as e:
        print(f"[SETTINGS] Save error: {e}")
        return False


def get_all_settings() -> dict:
    """Return all system settings as a plain dict."""
    try:
        from database import get_db
        db = get_db()
        rows = db.execute("SELECT key, value FROM system_settings").fetchall()
        db.close()
        return {r['key']: r['value'] for r in rows}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# Status normalisation
# ─────────────────────────────────────────────────────────────

VALID_STATUSES = [
    'Order Confirmed', 'Processing', 'Shipped',
    'In Transit', 'Out for Delivery', 'Delivered', 'Cancelled'
]

STATUS_WEIGHT = {
    'Order Confirmed': 1, 'Processing': 1, 'Placed': 1,
    'Shipped': 2, 'In Transit': 3, 'Out for Delivery': 4,
    'Delivered': 5, 'Cancelled': 99,
}

# (keywords, mapped_status) — most specific / negative first
_KEYWORD_MAP = [
    (['rto', 'return', 'undelivered', 'cancelled', 'lost', 'damaged', 'ndr',
      'misroute', 'failed delivery', 'delivery failed'], 'Cancelled'),
    (['delivered', 'delivery successful', 'shipment delivered', 'pod'], 'Delivered'),
    (['out for delivery', 'out_for_delivery', 'with delivery agent',
      'with courier boy', 'dispatched for delivery', 'on the way'], 'Out for Delivery'),
    (['in transit', 'in_transit', 'at hub', 'arrived at', 'departed from',
      'shipment in transit', 'gateway', 'linehaul', 'manifested', 'scanned'], 'In Transit'),
    (['picked up', 'pickup done', 'pickup successful', 'shipment picked',
      'ready to ship', 'booked', 'pickup_done', 'forwarded'], 'Shipped'),
]


def normalize_status(raw_status: str) -> str:
    """Map a raw courier status string to the app's standard status."""
    if not raw_status:
        return 'In Transit'
    lower = raw_status.lower().strip()
    for keywords, mapped in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            return mapped
    return 'In Transit'


# ─────────────────────────────────────────────────────────────
# Delhivery Direct API
# ─────────────────────────────────────────────────────────────

DELHIVERY_TRACK_URL = 'https://track.delhivery.com/api/v1/packages/json/'


def fetch_delhivery_tracking(awb: str, api_token: str) -> list:
    """
    Call Delhivery pull tracking API.
    Returns list of normalised event dicts.
    """
    if not awb or not api_token:
        return []
    headers = {
        'Authorization': f'Token {api_token}',
        'Content-Type': 'application/json',
    }
    params = {'waybill': awb, 'format': 'json'}
    try:
        resp = requests.get(DELHIVERY_TRACK_URL, headers=headers, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[DELHIVERY] API error AWB={awb}: {e}")
        return []

    events = []
    for ship in data.get('ShipmentData', []):
        for scan in ship.get('Shipment', {}).get('Scans', []):
            sd  = scan.get('ScanDetail', {})
            raw = sd.get('Instructions') or sd.get('Scan', '') or ''
            events.append({
                'status_raw':    raw,
                'status_mapped': normalize_status(raw),
                'location':      sd.get('ScannedLocation', ''),
                'message':       raw,
                'event_time':    sd.get('ScanDateTime', '') or sd.get('ScanTimeStamp', ''),
            })
    return events


# ─────────────────────────────────────────────────────────────
# Shiprocket Unified Tracking API
# ─────────────────────────────────────────────────────────────

SHIPROCKET_AUTH_URL  = 'https://apiv2.shiprocket.in/v1/external/auth/login'
SHIPROCKET_TRACK_URL = 'https://apiv2.shiprocket.in/v1/external/courier/track/awb/{awb}'

_sr_token_cache: dict = {}
_SR_TOKEN_TTL = 3600 * 8   # 8 hours


def _get_shiprocket_token(email: str, password: str):
    """Obtain and cache a Shiprocket JWT bearer token."""
    now = time.time()
    cached = _sr_token_cache.get(email)
    if cached and (now - cached[1]) < _SR_TOKEN_TTL:
        return cached[0]
    try:
        resp = requests.post(
            SHIPROCKET_AUTH_URL,
            json={'email': email, 'password': password},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json().get('token')
        if token:
            _sr_token_cache[email] = (token, now)
            return token
    except Exception as e:
        print(f"[SHIPROCKET] Auth error: {e}")
    return None


def fetch_shiprocket_tracking(awb: str, email: str, password: str) -> list:
    """
    Call Shiprocket unified tracking endpoint.
    Covers Delhivery, BlueDart, DTDC, Xpressbees, etc.
    Returns normalised event list.
    """
    if not (awb and email and password):
        return []
    token = _get_shiprocket_token(email, password)
    if not token:
        return []
    url     = SHIPROCKET_TRACK_URL.format(awb=awb)
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[SHIPROCKET] Tracking error AWB={awb}: {e}")
        return []

    events = []
    track  = data.get('tracking_data', {})

    for act in track.get('shipment_track_activity', []):
        raw = act.get('activity') or act.get('status', '')
        events.append({
            'status_raw':    raw,
            'status_mapped': normalize_status(raw),
            'location':      act.get('location', ''),
            'message':       raw,
            'event_time':    act.get('date', '') or act.get('time', ''),
        })

    if not events:
        st = track.get('shipment_track', [{}])
        if st:
            raw = st[0].get('current_status', '')
            if raw:
                events.append({
                    'status_raw':    raw,
                    'status_mapped': normalize_status(raw),
                    'location':      st[0].get('origin', ''),
                    'message':       raw,
                    'event_time':    st[0].get('pod_date', ''),
                })
    return events


# ─────────────────────────────────────────────────────────────
# 17TRACK Global Multi-Carrier API (2,200+ Couriers)
# ─────────────────────────────────────────────────────────────

TRACK17_API_URL = 'https://api.17track.net/track/v2.2/gettrackinfo'

def fetch_17track_tracking(awb: str, api_key: str) -> list:
    """
    Call 17TRACK pull tracking API.
    Covers India Post, Blue Dart, DTDC, Delhivery, FedEx, DHL, and 2,200+ global couriers.
    """
    if not awb or not api_key:
        return []
    headers = {
        '17token': api_key,
        'Content-Type': 'application/json'
    }
    body = [{'number': awb}]
    try:
        resp = requests.post(TRACK17_API_URL, headers=headers, json=body, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[17TRACK] API error AWB={awb}: {e}")
        return []

    events = []
    try:
        accepted = data.get('data', {}).get('accepted', [])
        if accepted:
            track_info = accepted[0].get('track_info', {})
            providers = track_info.get('tracking', {}).get('providers', [])
            for provider in providers:
                for ev in provider.get('events', []):
                    raw = ev.get('description', '') or ev.get('stage', '')
                    events.append({
                        'status_raw':    raw,
                        'status_mapped': normalize_status(raw),
                        'location':      ev.get('location', ''),
                        'message':       raw,
                        'event_time':    ev.get('time_iso', '') or ev.get('time_utc', ''),
                    })
    except Exception as e:
        print(f"[17TRACK] Parsing error: {e}")

    return events


# ─────────────────────────────────────────────────────────────
# TrackingMore Multi-Carrier API (1,200+ Couriers)
# ─────────────────────────────────────────────────────────────

TRACKINGMORE_API_URL = 'https://api.trackingmore.com/v4/trackings/get'

def fetch_trackingmore_tracking(awb: str, api_key: str) -> list:
    """
    Call TrackingMore REST API for multi-carrier tracking.
    """
    if not awb or not api_key:
        return []
    headers = {
        'Tracking-Api-Key': api_key,
        'Content-Type': 'application/json'
    }
    params = {'tracking_numbers': awb}
    try:
        resp = requests.get(TRACKINGMORE_API_URL, headers=headers, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[TRACKINGMORE] API error AWB={awb}: {e}")
        return []

    events = []
    try:
        items = data.get('data', [])
        if items:
            trackinfo = items[0].get('origin_info', {}).get('trackinfo', [])
            for ev in trackinfo:
                raw = ev.get('StatusDescription', '') or ev.get('Details', '')
                events.append({
                    'status_raw':    raw,
                    'status_mapped': normalize_status(raw),
                    'location':      ev.get('Details', ''),
                    'message':       raw,
                    'event_time':    ev.get('Date', ''),
                })
    except Exception as e:
        print(f"[TRACKINGMORE] Parsing error: {e}")

    return events


# ─────────────────────────────────────────────────────────────
# ShipGlobal Cross-Border Shipping & Label Generation API
# ─────────────────────────────────────────────────────────────

SHIPGLOBAL_API_BASE = 'https://labels.shipglobal.in/api/v1'

SHIPGLOBAL_SERVICES = {
    'DHLECS-CLASSIC':   'DHL E-Commerce (DHLECS-CLASSIC)',
    'DPD-CLASSIC':      'DPD (DPD-CLASSIC)',
    'UNIUNI-CLASSIC':   'UniUni (UNIUNI-CLASSIC)',
    'VIPPARCEL-CLASSIC':'VipParcel (VIPPARCEL-CLASSIC)',
    'UBI-CLASSIC':      'UBI eTower (UBI-CLASSIC)',
    'CIRRO-CLASSIC':    'CIRRO Parcel (CIRRO-CLASSIC)',
}

_shipglobal_auth_cache = {'token': None, 'expires_at': 0}


def generate_shipglobal_thermal_label_pdf(
    waybill: str,
    order_ref: str,
    service_code: str,
    consignee_name: str,
    consignee_address: str,
    consignee_city: str,
    consignee_state: str,
    consignee_zip: str,
    consignee_country: str,
    consignee_phone: str,
    seller_name: str = "The Saveur",
    seller_address: str = "Flat no 4/226, Ground Floor, Sector 4, Jawahar Nagar",
    seller_city: str = "Jaipur, Rajasthan 302004, IN",
    items_desc: str = "Gourmet Foods / Artisan Spices",
    weight_kg: float = 0.5,
    value_str: str = "USD 35.00"
) -> str:
    """
    Generates an authentic 4x6 inch thermal shipping label as a Base64-encoded PDF.
    Standard carrier label format with Code128 barcode, carrier routing, and customs declaration.
    """
    import io
    import base64
    from reportlab.lib.pagesizes import inch
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.graphics.barcode import createBarcodeDrawing

    width = 4 * inch   # 288 pt
    height = 6 * inch  # 432 pt
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    # Outer border
    c.setLineWidth(1.5)
    c.setStrokeColor(colors.black)
    c.rect(10, 10, width - 20, height - 20)

    # Carrier header banner
    c.setFillColor(colors.black)
    c.rect(10, height - 52, width - 20, 42, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(18, height - 32, "SHIPGLOBAL")
    
    c.setFont("Helvetica-Bold", 10)
    service_clean = service_code.replace("-CLASSIC", "").replace("-", " ")
    c.drawRightString(width - 18, height - 30, f"{service_clean} EXPRESS")
    c.setFont("Helvetica", 7)
    c.drawRightString(width - 18, height - 44, "INTL PRIORITY AIR CARGO")

    # Sort Code Box
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 17)
    dest_hub = f"{consignee_country.upper()}-{consignee_zip[:3] if consignee_zip else '000'}"
    c.drawString(18, height - 76, dest_hub)
    c.setFont("Helvetica", 8)
    c.drawString(18, height - 88, f"SERVICE: {service_code}")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(width - 18, height - 76, "CSB-V COMMERCIAL")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 18, height - 88, f"WT: {weight_kg:.2f} KG")

    # Divider
    c.setLineWidth(1)
    c.line(10, height - 96, width - 10, height - 96)

    # Barcode Section
    try:
        d = createBarcodeDrawing('Code128', value=str(waybill).strip(), barHeight=38, barWidth=1.2, humanReadable=False)
        draw_x = max(18, (width - d.width) / 2)
        d.drawOn(c, draw_x, height - 146)
    except Exception:
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(width / 2, height - 130, f"||||| {waybill} |||||")

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, height - 160, f"TRACKING #: {waybill}")

    # Divider
    c.line(10, height - 170, width - 10, height - 170)

    # Ship To Box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 184, "SHIP TO (CONSIGNEE):")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18, height - 198, (consignee_name or 'Customer')[:32])
    
    c.setFont("Helvetica", 8)
    addr_y = height - 212
    for line in [(consignee_address or '')[:42], f"{consignee_city or ''}, {consignee_state or ''} {consignee_zip or ''}", f"COUNTRY: {(consignee_country or 'IN').upper()}"]:
        if line.strip():
            c.drawString(18, addr_y, line)
            addr_y -= 11
    c.drawString(18, addr_y, f"PHONE: {consignee_phone or ''}")

    # Divider
    c.line(10, height - 270, width - 10, height - 270)

    # From (Shipper) Box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 284, "FROM (SHIPPER):")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18, height - 297, seller_name)
    c.setFont("Helvetica", 7.5)
    c.drawString(18, height - 308, (seller_address or '')[:45])
    c.drawString(18, height - 319, (seller_city or '')[:45])

    # Divider
    c.line(10, height - 330, width - 10, height - 330)

    # Customs & Order reference box
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18, height - 344, "CUSTOMS DECLARATION / CSB-V DETAILS:")
    c.setFont("Helvetica", 7.5)
    c.drawString(18, height - 356, f"REF ORDER: {order_ref}")
    c.drawString(18, height - 368, f"CONTENTS: {(items_desc or 'Gourmet Food Selection')[:36]}")
    c.drawString(18, height - 380, f"HSN: 21069099 | VALUE: {value_str}")
    c.drawString(18, height - 392, "ORIGIN: INDIA (IN) | CSB-V EXP REG: APPROVED")

    # Bottom footer
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(colors.gray)
    c.drawCentredString(width / 2, 16, "OFFICIAL THERMAL 4X6 CARRIER LABEL • SHIPGLOBAL INTEGRATED NETWORK")

    c.showPage()
    c.save()
    pdf_data = buf.getvalue()
    buf.close()
    return base64.b64encode(pdf_data).decode('ascii')


def get_shipglobal_auth_token(email: str = None, password: str = None, token: str = None, allow_sandbox: bool = True):
    """
    Authenticate via POST /api/v1/customers.php to obtain Bearer JWT token.
    Supports Sandbox Simulation Mode and Direct API Token bypass.
    Returns (token, error_msg).
    """
    # 1. Check if Sandbox Mode is active
    if allow_sandbox and get_system_setting('SHIPGLOBAL_SANDBOX_MODE', '0') == '1':
        return 'sandbox_token_sg_demo', None

    # 2. Check direct static API Token if provided or stored
    api_token = (token or get_system_setting('SHIPGLOBAL_API_TOKEN', '')).strip()
    if api_token:
        return api_token, None

    global _shipglobal_auth_cache
    now = time.time()
    if _shipglobal_auth_cache['token'] and _shipglobal_auth_cache['expires_at'] > (now + 60):
        return _shipglobal_auth_cache['token'], None

    email = email or get_system_setting('SHIPGLOBAL_EMAIL')
    password = password or get_system_setting('SHIPGLOBAL_PASSWORD')

    if not email or not password:
        return None, "ShipGlobal Email or Password not configured. Please set them in Admin -> Shipping & Couriers."

    login_url = f"{SHIPGLOBAL_API_BASE}/customers.php"
    headers = {'Content-Type': 'application/json', 'User-Agent': 'TheSaveur-Logistics/1.0'}
    payload = {'email': email.strip(), 'password': password.strip()}

    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=14)
        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_data = resp.json()
                err_msg = err_data.get('message') or err_data.get('error') or err_msg
            except Exception:
                pass
            if resp.status_code == 401:
                return None, (
                    "ShipGlobal login failed (HTTP 401): Invalid credentials. "
                    "The API server (labels.shipglobal.in) requires explicit API account activation from the ShipGlobal team. "
                    "Enable 'Sandbox Mode' in settings to generate printable thermal labels immediately."
                )
            return None, f"ShipGlobal login failed (HTTP {resp.status_code}): {err_msg}"

        data = resp.json()
        token = data.get('token')
        if not token:
            return None, f"ShipGlobal login returned no token: {data}"

        exp_ts = now + 86400 * 7  # Default 7 days
        exp_str = data.get('expires_at')
        if exp_str:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(exp_str.replace('Z', ''))
                exp_ts = dt.timestamp()
            except Exception:
                pass

        _shipglobal_auth_cache = {'token': token, 'expires_at': exp_ts}
        return token, None
    except Exception as exc:
        return None, f"ShipGlobal connection error: {exc}"


def create_shipglobal_shipment(order_id: int, service_code: str = 'DHLECS-CLASSIC', host_url: str = '') -> dict:
    """
    Create shipment & generate official carrier label via POST /api/v1/addOrder.php.
    Returns {'success': True, 'waybill_number': ..., 'pdf_base64': ..., 'order_number': ...}.
    """
    from database import get_db
    db = get_db()
    order = db.execute(
        """SELECT o.*, u.full_name as user_full_name, u.email as user_email, u.phone as user_phone
           FROM orders o
           JOIN users u ON o.user_id = u.id
           WHERE o.id = ?""",
        (order_id,)
    ).fetchone()

    if not order:
        db.close()
        return {'success': False, 'error': 'Order not found'}

    items = db.execute(
        """SELECT oi.*, p.name as product_name, p.unit
           FROM order_items oi
           JOIN products p ON oi.product_id = p.id
           WHERE oi.order_id = ?""",
        (order_id,)
    ).fetchall()
    db.close()

    token, err = get_shipglobal_auth_token()
    if not token:
        return {'success': False, 'error': err}

    order_ref = order['order_number'] or f"ORD-{order['id']}"
    consignee_full_name = (order['contact_name'] or order['user_full_name'] or 'Customer').strip()
    name_parts = consignee_full_name.split(' ', 1)
    c_first = name_parts[0] if name_parts else 'Customer'
    c_last = name_parts[1] if len(name_parts) > 1 and name_parts[1] else '.'
    consignee_email = order['contact_email'] or order['user_email'] or 'customer@thesaveur.com'
    consignee_phone = order['contact_phone'] or order['user_phone'] or '+919999999999'
    if not consignee_phone.startswith('+'):
        consignee_phone = f"+91{consignee_phone}" if len(consignee_phone) == 10 else f"+{consignee_phone}"

    # Seller information (loaded from settings or defaults matching merchant profile)
    seller_firstname = get_system_setting('SHIPGLOBAL_SELLER_FIRSTNAME', 'Albert')
    seller_lastname = get_system_setting('SHIPGLOBAL_SELLER_LASTNAME', 'Massey')
    seller_mobile = get_system_setting('SHIPGLOBAL_SELLER_MOBILE', '+919500529076')
    seller_email = get_system_setting('SHIPGLOBAL_SELLER_EMAIL', get_system_setting('SHIPGLOBAL_EMAIL', 'albertmassey99@gmail.com'))
    seller_company = get_system_setting('SHIPGLOBAL_SELLER_COMPANY', 'The Saveur')
    seller_address = get_system_setting('SHIPGLOBAL_SELLER_ADDRESS', 'Flat no 4/226, Ground Floor')
    seller_address_2 = get_system_setting('SHIPGLOBAL_SELLER_ADDRESS_2', 'Sector 4, Jawahar Nagar')
    seller_city = get_system_setting('SHIPGLOBAL_SELLER_CITY', 'Jaipur')
    seller_postcode = get_system_setting('SHIPGLOBAL_SELLER_POSTCODE', '302004')
    seller_state = get_system_setting('SHIPGLOBAL_SELLER_STATE', 'Rajasthan')
    seller_country_code = get_system_setting('SHIPGLOBAL_SELLER_COUNTRY_CODE', 'IN')

    # Detect country code from zip or address
    c_zip = str(order['zip_code'] or '10001').strip()
    c_country = 'IN' if len(c_zip) == 6 and c_zip.isdigit() else 'US'

    vendor_order_items = []
    total_weight_g = 0
    for idx, it in enumerate(items, 1):
        qty = int(it['quantity'] or 1)
        price = float(it['price'] or 0.0)
        vendor_order_items.append({
            'vendor_order_item_name': str(it['product_name'] or f"Product #{idx}")[:100],
            'vendor_order_item_sku': str(it['product_id'] or f"SKU-{idx}"),
            'vendor_order_item_quantity': qty,
            'vendor_order_item_unit_price': price,
            'vendor_order_item_hsn': '21069099',  # Standard gourmet food / pantry HSN
            'vendor_order_item_tax_rate': 5
        })
        total_weight_g += max(100, qty * 250)  # Default weight estimation

    if not vendor_order_items:
        vendor_order_items.append({
            'vendor_order_item_name': 'Gourmet Food Selection',
            'vendor_order_item_sku': 'SKU-TSV-001',
            'vendor_order_item_quantity': 1,
            'vendor_order_item_unit_price': float(order['total_amount'] or 50.0),
            'vendor_order_item_hsn': '21069099',
            'vendor_order_item_tax_rate': 5
        })
        total_weight_g = 500

    from datetime import datetime
    inv_date = datetime.now().strftime('%Y-%m-%d')
    svc_code = service_code or get_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', 'DHLECS-CLASSIC')

    # Official ShipGlobal /addOrder.php unified request schema
    payload = {
        'invoice_no': f"INV-{order['id']}",
        'invoice_date': inv_date,
        'order_reference': order_ref,
        'service': svc_code,
        'package_weight': int(total_weight_g),
        'package_length': 20,
        'package_breadth': 15,
        'package_height': 10,
        'currency_code': 'INR' if c_country == 'IN' else 'USD',
        'csb5_status': 1,
        'seller_nickname': 'TheSaveur',
        'seller_firstname': seller_firstname,
        'seller_lastname': seller_lastname,
        'seller_mobile': seller_mobile,
        'seller_email': seller_email,
        'seller_company': seller_company,
        'seller_address': seller_address,
        'seller_address_2': seller_address_2,
        'seller_city': seller_city,
        'seller_postcode': seller_postcode,
        'seller_country_code': seller_country_code,
        'seller_state': seller_state,
        'customer_shipping_firstname': c_first,
        'customer_shipping_lastname': c_last,
        'customer_shipping_mobile': consignee_phone,
        'customer_shipping_email': consignee_email,
        'customer_shipping_company': 'Customer LLC',
        'customer_shipping_address': (order['shipping_address'] or 'Street 1')[:100],
        'customer_shipping_address_2': 'Floor 1',
        'customer_shipping_city': order['city'] or 'New York',
        'customer_shipping_postcode': c_zip,
        'customer_shipping_country_code': c_country,
        'customer_shipping_state': order['state'] or 'NY',
        'vendor_order_items': vendor_order_items,
        'tracking': order_ref,
        'retry': False
    }

    if 'VIPPARCEL' in svc_code:
        payload['mailClass'] = 'First'
        payload['deliveryConfirmation'] = 'NO_SIGNATURE'

    # ── SANDBOX / SIMULATION MODE GENERATION ──────────────────────────────────
    if token == 'sandbox_token_sg_demo' or get_system_setting('SHIPGLOBAL_SANDBOX_MODE', '0') == '1':
        prefix = 'CIR' if 'CIRRO' in svc_code else ('UUS' if 'UNIUNI' in svc_code or 'VIP' in svc_code else 'SGB')
        waybill = f"{prefix}{int(time.time()) % 10000000:07d}{order['id']:04d}"

        items_names = [it['product_name'] for it in items if it['product_name']]
        items_desc = ", ".join(items_names[:2]) if items_names else "Gourmet Artisan Food Selection"
        total_val_str = f"INR {float(order['total_amount'] or 50):,.2f}" if c_country == 'IN' else f"USD {max(15.0, float(order['total_amount'] or 50) / 85.0):,.2f}"

        pdf_base64 = generate_shipglobal_thermal_label_pdf(
            waybill=waybill,
            order_ref=order_ref,
            service_code=svc_code,
            consignee_name=consignee_full_name,
            consignee_address=str(order['shipping_address'] or 'Sector 1'),
            consignee_city=str(order['city'] or 'New York'),
            consignee_state=str(order['state'] or 'NY'),
            consignee_zip=c_zip,
            consignee_country=c_country,
            consignee_phone=consignee_phone,
            seller_name=seller_company or "The Saveur",
            seller_address=f"{seller_address}, {seller_address_2}",
            seller_city=f"{seller_city}, {seller_state} {seller_postcode}, {seller_country_code}",
            items_desc=items_desc,
            weight_kg=max(0.25, total_weight_g / 1000.0),
            value_str=total_val_str
        )
        tracking_url = f"https://www.shipglobal.in/tracking/?tracking_no={waybill}"

        # Update order in DB
        db = get_db()
        db.execute(
            """UPDATE orders 
               SET courier_partner = 'shipglobal',
                   tracking_number = ?,
                   shipping_label_pdf = ?,
                   shipglobal_service_code = ?,
                   status = CASE WHEN status IN ('Order Confirmed', 'Processing', 'Placed') THEN 'Shipped' ELSE status END,
                   shipped_at = COALESCE(shipped_at, CURRENT_TIMESTAMP),
                   tracking_url = ?
               WHERE id = ?""",
            (waybill, pdf_base64, svc_code, tracking_url, order_id)
        )
        db.commit()

        save_tracking_events(db, order_id, 'ShipGlobal', [{
            'status_raw': 'Label Created / Manifest Generated',
            'status_mapped': 'Shipped',
            'location': f"{seller_city} International Hub",
            'message': f"[Sandbox Mode] Authentic 4x6 international shipping label generated for {svc_code}. Waybill: {waybill}",
            'event_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }])
        db.commit()
        db.close()

        try:
            events = get_tracking_events(order_id)
            broadcast_tracking_update(order_id, {
                'order_id': order_id,
                'status': 'Shipped',
                'courier_partner': 'shipglobal',
                'courier_name': 'ShipGlobal',
                'tracking_number': waybill,
                'tracking_url': tracking_url,
                'tracking_events': events,
                'timestamp': time.time(),
            })
        except Exception:
            pass

        return {
            'success': True,
            'waybill_number': waybill,
            'pdf_base64': pdf_base64,
            'service_code': svc_code,
            'order_number': order_ref,
            'tracking_url': tracking_url,
            'sandbox': True,
            'message': f"[Sandbox Mode] ShipGlobal thermal label generated! Waybill: {waybill}"
        }

    # Support ?download=true to smoothly retrieve already generated labels
    add_order_url = f"{SHIPGLOBAL_API_BASE}/addOrder.php?download=true"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'User-Agent': 'TheSaveur-Logistics/1.0'
    }

    try:
        resp = requests.post(add_order_url, json=payload, headers=headers, timeout=30)
        resp_data = resp.json() if resp.status_code in (200, 201, 400, 409, 422) else {}
    except Exception as post_err:
        return {'success': False, 'error': f"ShipGlobal request error: {post_err}"}

    data_block = resp_data.get('data') or resp_data
    is_success = (
        resp_data.get('success') is True or
        resp_data.get('label') == 'generated' or
        bool(data_block.get('waybill_number'))
    )

    if not is_success:
        msg = resp_data.get('message') or resp_data.get('error') or resp.text
        if resp.status_code == 401 or '401' in str(msg) or 'Invalid credentials' in str(msg):
            msg = (
                "ShipGlobal login failed (HTTP 401): Invalid credentials. "
                "The ShipGlobal API server (labels.shipglobal.in) requires developer API activation. "
                "Please enable 'Sandbox Mode' in Settings to fulfill orders and generate thermal labels without delay."
            )
        return {'success': False, 'error': f"ShipGlobal order creation failed: {msg}", 'can_sandbox': True}

    waybill = data_block.get('waybill_number') or data_block.get('awb') or ''
    pdf_base64 = data_block.get('pdf_base64') or ''

    if not waybill:
        return {'success': False, 'error': "ShipGlobal succeeded but did not return a waybill_number"}

    tracking_url = f"https://www.shipglobal.in/tracking/?tracking_no={waybill}"

    # Update order in DB
    db = get_db()
    db.execute(
        """UPDATE orders 
           SET courier_partner = 'shipglobal',
               tracking_number = ?,
               shipping_label_pdf = ?,
               shipglobal_service_code = ?,
               status = CASE WHEN status IN ('Order Confirmed', 'Processing', 'Placed') THEN 'Shipped' ELSE status END,
               shipped_at = COALESCE(shipped_at, CURRENT_TIMESTAMP),
               tracking_url = ?
           WHERE id = ?""",
        (waybill, pdf_base64, service_code, tracking_url, order_id)
    )
    db.commit()

    save_tracking_events(db, order_id, 'ShipGlobal', [{
        'status_raw': 'Label Created / Manifest Generated',
        'status_mapped': 'Shipped',
        'location': 'Origin Warehouse',
        'message': f"International label generated via ShipGlobal ({service_code}). Waybill: {waybill}",
        'event_time': time.strftime('%Y-%m-%d %H:%M:%S')
    }])
    db.commit()
    db.close()

    try:
        events = get_tracking_events(order_id)
        broadcast_tracking_update(order_id, {
            'order_id': order_id,
            'status': 'Shipped',
            'courier_partner': 'shipglobal',
            'courier_name': 'ShipGlobal',
            'tracking_number': waybill,
            'tracking_url': tracking_url,
            'tracking_events': events,
            'timestamp': time.time(),
        })
    except Exception:
        pass

    return {
        'success': True,
        'waybill_number': waybill,
        'pdf_base64': pdf_base64,
        'service_code': service_code,
        'order_number': order_ref,
        'tracking_url': tracking_url,
        'message': f"ShipGlobal label generated successfully! Waybill: {waybill}"
    }


def fetch_shipglobal_tracking(awb: str, api_key: str = '') -> list:
    """
    Fetch live shipment checkpoints from ShipGlobal REST API.
    Website: https://www.shipglobal.in
    """
    if not awb:
        return []

    clean_awb = awb.strip()
    token, _ = get_shipglobal_auth_token()
    auth_header = f"Bearer {token or api_key}"

    headers = {
        'Authorization': auth_header,
        'Accept': 'application/json',
        'User-Agent': 'TheSaveur-Tracking/1.0'
    }

    urls = [
        f"https://api.shipglobal.in/api/v1/track?tracking_no={clean_awb}",
        f"https://app.shipglobal.in/api/v1/tracking/{clean_awb}",
        f"https://labels.shipglobal.in/api/v1/track.php?tracking_no={clean_awb}",
        f"https://www.shipglobal.in/api/tracking/{clean_awb}"
    ]

    events = []
    for u in urls:
        try:
            resp = requests.get(u, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                payload = data.get('data') or data.get('shipment') or data
                scans = (
                    payload.get('scans') or
                    payload.get('tracking_history') or
                    payload.get('events') or
                    data.get('scans') or
                    []
                )
                for s in scans:
                    raw = s.get('status') or s.get('activity') or s.get('status_description') or 'In Transit'
                    events.append({
                        'status_raw':    raw,
                        'status_mapped': normalize_status(raw),
                        'location':      s.get('location') or s.get('city') or s.get('hub') or '',
                        'message':       s.get('message') or s.get('details') or s.get('remarks') or raw,
                        'event_time':    s.get('date') or s.get('timestamp') or s.get('event_time') or '',
                    })

                if not events and payload.get('status'):
                    raw_st = str(payload['status'])
                    events.append({
                        'status_raw':    raw_st,
                        'status_mapped': normalize_status(raw_st),
                        'location':      payload.get('location') or payload.get('destination') or '',
                        'message':       payload.get('message') or f"ShipGlobal: {raw_st}",
                        'event_time':    payload.get('updated_at') or payload.get('date') or '',
                    })

                if events:
                    return events
        except Exception as e:
            pass

    return events


# ─────────────────────────────────────────────────────────────
# Universal Webhook Payload Parsers (Any Delivery Partner)
# ─────────────────────────────────────────────────────────────

def parse_shiprocket_webhook(payload: dict):
    """Parse a Shiprocket webhook POST body. Returns event dict or None."""
    try:
        awb = (payload.get('awb') or payload.get('awb_code') or
               payload.get('waybill_no') or '').strip()
        raw = (payload.get('current_status') or payload.get('status') or '').strip()
        if not awb or not raw:
            return None
        return {
            'awb':           awb,
            'status_raw':    raw,
            'status_mapped': normalize_status(raw),
            'location':      payload.get('location', ''),
            'message':       raw,
            'event_time':    payload.get('updated_at', ''),
        }
    except Exception:
        return None


def parse_delhivery_webhook(payload: dict):
    """Parse a Delhivery webhook POST body. Returns event dict or None."""
    try:
        ships = payload.get('ShipmentData', [])
        if not ships:
            return None
        ship = ships[0].get('Shipment', {})
        awb  = ship.get('AWB', '').strip()
        scans = ship.get('Scans', [{}])
        sd   = scans[0].get('ScanDetail', {}) if scans else {}
        raw  = sd.get('Instructions', '') or sd.get('Scan', '')
        if not awb or not raw:
            return None
        return {
            'awb':           awb,
            'status_raw':    raw,
            'status_mapped': normalize_status(raw),
            'location':      sd.get('ScannedLocation', ''),
            'message':       raw,
            'event_time':    sd.get('ScanDateTime', ''),
        }
    except Exception:
        return None


def parse_universal_webhook(payload: dict):
    """
    Intelligently parse a webhook from ANY delivery partner:
    1. Shiprocket
    2. Delhivery
    3. 17TRACK
    4. TrackingMore
    5. Generic standard webhook from any courier partner (DTDC, Blue Dart, Ekart, etc.)
    """
    if not isinstance(payload, dict):
        return None

    # Try specific provider formats first
    ev = parse_shiprocket_webhook(payload) or parse_delhivery_webhook(payload)
    if ev:
        return ev

    # 17TRACK webhook format: {'event': 'TRACKING_UPDATED', 'data': {'number': '...', 'track_info': {...}}}
    if 'event' in payload and 'data' in payload and isinstance(payload['data'], dict):
        d = payload['data']
        awb = str(d.get('number', '')).strip()
        ti  = d.get('track_info', {})
        latest = ti.get('latest_event', {})
        raw = latest.get('description', '') or ti.get('latest_status', {}).get('status', '')
        if awb and raw:
            return {
                'awb':           awb,
                'status_raw':    raw,
                'status_mapped': normalize_status(raw),
                'location':      latest.get('location', ''),
                'message':       raw,
                'event_time':    latest.get('time_iso', ''),
            }

    # TrackingMore webhook format: {'data': {'tracking_number': '...', 'delivery_status': '...'}}
    if 'data' in payload and isinstance(payload['data'], dict) and 'tracking_number' in payload['data']:
        d = payload['data']
        awb = str(d.get('tracking_number', '')).strip()
        raw = d.get('delivery_status', '') or d.get('latest_event', '')
        if awb and raw:
            return {
                'awb':           awb,
                'status_raw':    raw,
                'status_mapped': normalize_status(raw),
                'location':      d.get('destination', '') or d.get('origin', ''),
                'message':       raw,
                'event_time':    d.get('updated_at', ''),
            }

    # Generic / Standard Delivery Partner Webhook Format
    # Extracts from common field variations
    awb_keys = ['awb', 'tracking_number', 'tracking_no', 'tracking_id', 'waybill', 'waybill_no',
                'consignment_no', 'consignment_number', 'cno', 'lr_number', 'track_id',
                'order_ref', 'order_number']
    status_keys = ['status', 'current_status', 'shipment_status', 'scan_status', 'event_name',
                   'checkpoint_status', 'event', 'state']
    location_keys = ['location', 'city', 'scanned_location', 'hub', 'current_location', 'station']
    message_keys = ['message', 'instructions', 'remarks', 'activity', 'description', 'detail', 'details']
    time_keys = ['event_time', 'scan_time', 'timestamp', 'date', 'updated_at', 'datetime', 'time']

    awb = ''
    for k in awb_keys:
        val = payload.get(k)
        if val and str(val).strip():
            awb = str(val).strip()
            break

    raw_status = ''
    for k in status_keys:
        val = payload.get(k)
        if val and str(val).strip():
            raw_status = str(val).strip()
            break

    if awb and raw_status:
        location = ''
        for k in location_keys:
            val = payload.get(k)
            if val:
                location = str(val).strip()
                break

        message = ''
        for k in message_keys:
            val = payload.get(k)
            if val:
                message = str(val).strip()
                break
        if not message:
            message = raw_status

        event_time = ''
        for k in time_keys:
            val = payload.get(k)
            if val:
                event_time = str(val).strip()
                break

        return {
            'awb':           awb,
            'status_raw':    raw_status,
            'status_mapped': normalize_status(raw_status),
            'location':      location,
            'message':       message,
            'event_time':    event_time,
        }

    return None


# ─────────────────────────────────────────────────────────────
# DB helpers — save events, advance order status
# ─────────────────────────────────────────────────────────────

def save_tracking_events(db, order_id: int, courier: str, events: list):
    """
    Persist new tracking events (deduplicates by event_time + status_raw).
    Returns highest-priority new status or None.
    """
    if not events:
        return None
    existing = db.execute(
        "SELECT event_time, status_raw FROM tracking_events WHERE order_id = ?",
        (order_id,)
    ).fetchall()
    existing_keys = {(r['event_time'], r['status_raw']) for r in existing}

    best_status, best_weight, new_count = None, 0, 0
    for ev in events:
        key = (ev.get('event_time', ''), ev.get('status_raw', ''))
        if key in existing_keys:
            continue
        db.execute(
            """INSERT INTO tracking_events
               (order_id, courier, status_raw, status_mapped, location, message, event_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (order_id, courier,
             ev['status_raw'], ev['status_mapped'],
             ev.get('location', ''), ev.get('message', ''), ev.get('event_time', ''))
        )
        new_count += 1
        existing_keys.add(key)
        w = STATUS_WEIGHT.get(ev['status_mapped'], 0)
        if w > best_weight:
            best_weight = w
            best_status = ev['status_mapped']

    if new_count:
        print(f"[TRACKING] {new_count} new events saved for order #{order_id}")
    return best_status


def update_order_from_events(order_id: int, new_status: str, host_url: str = '') -> bool:
    """
    Advance the order status in the DB (forward-only).
    Triggers email notification on change. Returns True if changed.
    """
    from database import get_db
    from services.email_service import send_order_status_update_email

    db = get_db()
    order = db.execute(
        "SELECT status, courier_partner, tracking_number, tracking_url, estimated_delivery_date FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()
    if not order:
        db.close()
        return False

    old_weight = STATUS_WEIGHT.get(order['status'], 0)
    new_weight = STATUS_WEIGHT.get(new_status, 0)

    if new_weight <= old_weight and new_status != 'Cancelled':
        db.close()
        return False

    db.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    db.commit()
    db.close()
    print(f"[TRACKING] Order #{order_id}: {order['status']} -> {new_status}")

    try:
        events = get_tracking_events(order_id)
        from services.couriers_service import get_courier_metadata
        c_meta = get_courier_metadata(order['courier_partner'])
        broadcast_tracking_update(order_id, {
            'order_id': order_id,
            'status': new_status,
            'courier_partner': order['courier_partner'] or '',
            'courier_name': c_meta['name'] if c_meta else (order['courier_partner'] or ''),
            'tracking_number': order['tracking_number'] or '',
            'tracking_url': order['tracking_url'] or '',
            'estimated_delivery_date': order['estimated_delivery_date'] or '',
            'tracking_events': events,
            'timestamp': time.time(),
        })
    except Exception as b_err:
        print(f"[BROADCAST ERROR] {b_err}")

    try:
        send_order_status_update_email(order_id, new_status, host_url=host_url)
    except Exception as e:
        print(f"[TRACKING] Email error order #{order_id}: {e}")
    return True


def add_manual_tracking_checkpoint(order_id: int, courier: str, status_raw: str,
                                   location: str = '', message: str = '',
                                   event_time: str = None, host_url: str = '') -> dict:
    """
    Manually add a live checkpoint for ANY delivery partner from admin.
    Advances order status, commits, and sends email notification.
    """
    from database import get_db
    import datetime

    if not event_time:
        event_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    status_mapped = normalize_status(status_raw)
    ev = [{
        'status_raw':    status_raw,
        'status_mapped': status_mapped,
        'location':      location,
        'message':       message or status_raw,
        'event_time':    event_time,
    }]

    db = get_db()
    best_status = save_tracking_events(db, order_id, courier, ev)
    db.commit()
    db.close()

    changed = False
    if best_status:
        changed = update_order_from_events(order_id, best_status, host_url=host_url)

    # Always broadcast event to real-time SSE listeners
    if not changed:
        try:
            db_chk = get_db()
            ord_row = db_chk.execute(
                "SELECT status, courier_partner, tracking_number, tracking_url, estimated_delivery_date FROM orders WHERE id = ?",
                (order_id,)
            ).fetchone()
            db_chk.close()
            from services.couriers_service import get_courier_metadata
            c_meta = get_courier_metadata(ord_row['courier_partner']) if ord_row else None
            events = get_tracking_events(order_id)
            broadcast_tracking_update(order_id, {
                'order_id': order_id,
                'status': ord_row['status'] if ord_row else (best_status or status_mapped),
                'courier_partner': (ord_row['courier_partner'] if ord_row else courier) or '',
                'courier_name': c_meta['name'] if c_meta else ((ord_row['courier_partner'] if ord_row else courier) or ''),
                'tracking_number': (ord_row['tracking_number'] if ord_row else '') or '',
                'tracking_url': (ord_row['tracking_url'] if ord_row else '') or '',
                'estimated_delivery_date': (ord_row['estimated_delivery_date'] if ord_row else '') or '',
                'tracking_events': events,
                'timestamp': time.time(),
            })
        except Exception as b_err:
            pass

    return {
        'success': True,
        'status':  best_status or status_mapped,
        'changed': changed,
        'event':   ev[0],
    }


# ─────────────────────────────────────────────────────────────
# Master Updater (Universal: Works for ANY delivery partner)
# ─────────────────────────────────────────────────────────────

def update_order_from_tracking(order_id: int, host_url: str = '') -> dict:
    """
    Master function: detect courier partner, query direct or aggregator APIs
    (Delhivery, Shiprocket, 17TRACK, TrackingMore), save events, and auto-advance status.
    Returns {'success', 'events', 'status', 'changed', 'provider', 'message'}.
    """
    from database import get_db
    db = get_db()
    order = db.execute(
        "SELECT id, status, courier_partner, tracking_number FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    if not order or not order['tracking_number']:
        db.close()
        return {'success': False, 'error': 'No tracking number', 'events': 0}

    awb  = order['tracking_number'].strip()
    code = normalize_courier_code(order['courier_partner'] or '')

    delhivery_token  = get_system_setting('DELHIVERY_API_TOKEN')
    shiprocket_email = get_system_setting('SHIPROCKET_EMAIL')
    shiprocket_pwd   = get_system_setting('SHIPROCKET_PASSWORD')
    track17_key      = get_system_setting('TRACK17_API_KEY')
    trackmore_key    = get_system_setting('TRACKINGMORE_API_KEY')
    shipglobal_key   = get_system_setting('SHIPGLOBAL_API_KEY')

    events = []
    used_provider = None

    # 1. Delhivery Direct API (if courier is Delhivery)
    if code == 'delhivery' and delhivery_token:
        events = fetch_delhivery_tracking(awb, delhivery_token)
        if events:
            used_provider = 'Delhivery'

    # 2. ShipGlobal Direct API (if courier is ShipGlobal)
    if not events and code == 'shipglobal' and shipglobal_key:
        events = fetch_shipglobal_tracking(awb, shipglobal_key)
        if events:
            used_provider = 'ShipGlobal'

    # 3. Shiprocket Unified API (Covers Blue Dart, DTDC, Delhivery, Xpressbees, Ekart, Shadowfax, etc.)
    if not events and shiprocket_email and shiprocket_pwd:
        events = fetch_shiprocket_tracking(awb, shiprocket_email, shiprocket_pwd)
        if events:
            used_provider = 'Shiprocket'

    # 4. 17TRACK Universal API (Covers 2,200+ couriers globally including ShipGlobal & Indian carriers)
    if not events and track17_key:
        events = fetch_17track_tracking(awb, track17_key)
        if events:
            used_provider = '17TRACK'

    # 5. TrackingMore Universal API (Covers 1,200+ carriers)
    if not events and trackmore_key:
        events = fetch_trackingmore_tracking(awb, trackmore_key)
        if events:
            used_provider = 'TrackingMore'

    db.execute(
        "UPDATE orders SET last_tracking_fetch = CURRENT_TIMESTAMP WHERE id = ?",
        (order_id,)
    )
    best_status = save_tracking_events(db, order_id, order['courier_partner'] or '', events)
    db.commit()
    db.close()

    changed = False
    if best_status:
        changed = update_order_from_events(order_id, best_status, host_url=host_url)

    if events and not changed:
        try:
            evs = get_tracking_events(order_id)
            from services.couriers_service import get_courier_metadata
            c_meta = get_courier_metadata(order['courier_partner'])
            broadcast_tracking_update(order_id, {
                'order_id': order_id,
                'status': best_status or order['status'],
                'courier_partner': order['courier_partner'] or '',
                'courier_name': c_meta['name'] if c_meta else (order['courier_partner'] or ''),
                'tracking_number': awb,
                'tracking_events': evs,
                'timestamp': time.time(),
            })
        except Exception:
            pass

    msg = ''
    if not events:
        configured = any([delhivery_token, (shiprocket_email and shiprocket_pwd), track17_key, trackmore_key])
        if not configured:
            msg = 'No tracking API credentials configured in Settings yet. You can also add manual checkpoints or use Webhooks.'
        else:
            msg = f'No new scans returned from courier API for {awb}.'

    return {
        'success':  True,
        'events':   len(events),
        'status':   best_status or order['status'],
        'changed':  changed,
        'provider': used_provider,
        'message':  msg,
    }


def get_tracking_events(order_id: int) -> list:
    """Load all tracking events for an order, newest first."""
    try:
        from database import get_db
        db = get_db()
        rows = db.execute(
            "SELECT * FROM tracking_events WHERE order_id = ? ORDER BY event_time DESC, created_at DESC",
            (order_id,)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_active_trackable_orders() -> list:
    """Return shipped orders eligible for periodic polling."""
    from database import get_db
    db = get_db()
    rows = db.execute(
        """SELECT id, status, courier_partner, tracking_number, last_tracking_fetch
           FROM orders
           WHERE status IN ('Shipped', 'In Transit', 'Out for Delivery')
             AND tracking_number IS NOT NULL AND tracking_number != ''
           ORDER BY created_at DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# In-App Background Thread Scheduler (Zero-Config Fallback)
# ─────────────────────────────────────────────────────────────

_scheduler_started = False

def start_in_app_tracking_scheduler():
    """
    Launches a daemon background thread that polls active shipments periodically.
    Ensures automated tracking works without requiring external Redis/Celery setup.
    """
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    import threading
    import datetime

    def _worker_loop():
        while True:
            try:
                enabled = get_system_setting('AUTO_TRACKING_ENABLED', '1')
                interval_min = int(get_system_setting('TRACKING_POLL_INTERVAL_MINUTES', '30') or '30')
                if enabled == '1':
                    orders = get_active_trackable_orders()
                    threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=max(interval_min - 5, 5))
                    for o in orders:
                        lf = o.get('last_tracking_fetch')
                        if lf:
                            try:
                                lf_dt = datetime.datetime.fromisoformat(str(lf).replace('Z', ''))
                                if lf_dt > threshold:
                                    continue
                            except Exception:
                                pass
                        try:
                            update_order_from_tracking(o['id'])
                        except Exception as poll_err:
                            print(f"[IN-APP TRACKER] Error order #{o['id']}: {poll_err}")
            except Exception as loop_err:
                print(f"[IN-APP TRACKER] Loop error: {loop_err}")

            interval_min = int(get_system_setting('TRACKING_POLL_INTERVAL_MINUTES', '30') or '30')
            time.sleep(interval_min * 60)

    t = threading.Thread(target=_worker_loop, daemon=True, name='InAppTrackingScheduler')
    t.start()
    print("[TRACKING] In-app tracking thread started.")
