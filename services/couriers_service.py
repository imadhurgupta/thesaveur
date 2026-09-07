"""
Smart Courier Tracking & Logistics Service for The Saveur
Maps courier partners to official tracking URL endpoints, brand colors, and badges.
"""

COURIER_PARTNERS = {
    'delhivery': {
        'name': 'Delhivery',
        'code': 'delhivery',
        'url_pattern': 'https://www.delhivery.com/track/package/{tracking_number}',
        'color': '#C8232B',
        'bg_color': 'rgba(200, 35, 43, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. 1401234567890 (12-14 digits)'
    },
    'bluedart': {
        'name': 'Blue Dart',
        'code': 'bluedart',
        'url_pattern': 'https://www.bluedart.com/tracking?track={tracking_number}',
        'color': '#003399',
        'bg_color': 'rgba(0, 51, 153, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. 89234567890 (9-11 digits)'
    },
    'dtdc': {
        'name': 'DTDC',
        'code': 'dtdc',
        'url_pattern': 'https://www.dtdc.in/tracking/tracking_results.asp?Ttype=awb_no&strCnno={tracking_number}',
        'color': '#D32F2F',
        'bg_color': 'rgba(211, 47, 47, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. D12345678 / Z12345678 (Consignment No)'
    },
    'indiapost': {
        'name': 'India Post (Speed Post)',
        'code': 'indiapost',
        'url_pattern': 'https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx',
        'color': '#C4122F',
        'bg_color': 'rgba(196, 18, 47, 0.08)',
        'icon_type': 'mail',
        'sample_format': 'e.g. EM123456789IN / ED123456789IN (13 chars)'
    },
    'xpressbees': {
        'name': 'Xpressbees',
        'code': 'xpressbees',
        'url_pattern': 'https://www.xpressbees.com/track?isawb=Yes&trackid={tracking_number}',
        'color': '#FF6A00',
        'bg_color': 'rgba(255, 106, 0, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. 138123456789 (AWB ID)'
    },
    'shadowfax': {
        'name': 'Shadowfax',
        'code': 'shadowfax',
        'url_pattern': 'https://tracker.shadowfax.in/#/track?awb={tracking_number}',
        'color': '#00A86B',
        'bg_color': 'rgba(0, 168, 107, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. SF123456789 (AWB)'
    },
    'ekart': {
        'name': 'Ekart Logistics',
        'code': 'ekart',
        'url_pattern': 'https://ekartlogistics.com/shipmenttrack/{tracking_number}',
        'color': '#0277BD',
        'bg_color': 'rgba(2, 119, 189, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. FMPC1234567890'
    },
    'amazon': {
        'name': 'Amazon Shipping (ATS)',
        'code': 'amazon',
        'url_pattern': 'https://track.amazon.in/tracking/{tracking_number}',
        'color': '#FF9900',
        'bg_color': 'rgba(255, 153, 0, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. TBA1234567890'
    },
    'fedex': {
        'name': 'FedEx',
        'code': 'fedex',
        'url_pattern': 'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'color': '#4D148C',
        'bg_color': 'rgba(77, 20, 140, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. 794812345678 (12 digits)'
    },
    'dhl': {
        'name': 'DHL Express',
        'code': 'dhl',
        'url_pattern': 'https://www.dhl.com/in-en/home/tracking/tracking-express.html?submit=1&tracking-id={tracking_number}',
        'color': '#D40511',
        'bg_color': 'rgba(212, 5, 17, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. 1234567890 (10 digits)'
    },
    'shiprocket': {
        'name': 'Shiprocket',
        'code': 'shiprocket',
        'url_pattern': 'https://shiprocket.co/tracking/{tracking_number}',
        'color': '#7C3AED',
        'bg_color': 'rgba(124, 58, 237, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. 1401234567890 (AWB / Tracking ID)'
    },
    'cirro': {
        'name': 'CIRRO Parcel',
        'code': 'cirro',
        'url_pattern': 'https://m.cirrotrack.com/{tracking_number}',
        'color': '#0284C7',
        'bg_color': 'rgba(2, 132, 199, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. GFUS01071582334210'
    },
    'shipglobal': {
        'name': 'ShipGlobal',
        'code': 'shipglobal',
        'url_pattern': 'https://shipglobal.in/tracking/?awb={tracking_number}',
        'color': '#059669',
        'bg_color': 'rgba(5, 150, 105, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. SG123456789IN / AWB'
    },
    'custom': {
        'name': 'Local / Custom Courier',
        'code': 'custom',
        'url_pattern': '{tracking_number}',
        'color': '#16A34A',
        'bg_color': 'rgba(22, 163, 74, 0.08)',
        'icon_type': 'package',
        'sample_format': 'Enter Tracking Number or Website URL'
    }
}


def get_custom_couriers_from_db():
    """Fetch saved custom couriers from the database."""
    try:
        from database import get_db
        db = get_db()
        rows = db.execute("SELECT * FROM custom_couriers ORDER BY name ASC").fetchall()
        db.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def normalize_courier_code(courier_partner):
    """Normalize courier partner string to a dictionary key."""
    if not courier_partner:
        return 'custom'
    key = courier_partner.lower().strip()
    key = key.replace(' ', '').replace('-', '').replace('_', '').replace('(', '').replace(')', '')
    
    if 'shiprocket' in key:
        return 'shiprocket'
    elif 'cirro' in key:
        return 'cirro'
    elif 'shipglobal' in key:
        return 'shipglobal'
    elif 'delhivery' in key:
        return 'delhivery'
    elif 'blue' in key or 'dart' in key:
        return 'bluedart'
    elif 'dtdc' in key:
        return 'dtdc'
    elif 'dhl' in key:
        return 'dhl'
    elif 'fedex' in key:
        return 'fedex'
    elif 'post' in key or 'india' in key or 'speedpost' in key:
        return 'indiapost'
    elif 'xpressbee' in key or 'xpress_bee' in key or 'bees' in key:
        return 'xpressbees'
    elif 'shadow' in key or 'fax' in key:
        return 'shadowfax'
    elif 'ekart' in key:
        return 'ekart'
    elif 'amazon' in key or 'ats' in key:
        return 'amazon'
    return courier_partner.strip()


def get_courier_metadata(courier_partner):
    """Get metadata dict for given courier partner string."""
    if not courier_partner:
        return COURIER_PARTNERS['custom'].copy()

    code = normalize_courier_code(courier_partner)
    if code in COURIER_PARTNERS:
        return COURIER_PARTNERS[code].copy()

    # Check custom couriers in database
    custom_list = get_custom_couriers_from_db()
    for cc in custom_list:
        if cc['code'].lower() == code.lower() or cc['name'].lower() == courier_partner.lower():
            return {
                'name': cc['name'],
                'code': cc['code'],
                'url_pattern': cc['url_pattern'] or '{tracking_number}',
                'color': cc.get('color') or '#16a34a',
                'bg_color': 'rgba(22, 163, 74, 0.08)',
                'icon_type': 'package',
                'sample_format': cc.get('sample_format') or 'Enter tracking number'
            }

    meta = COURIER_PARTNERS['custom'].copy()
    meta['name'] = courier_partner
    return meta


def format_tracking_url(pattern: str, tracking_number: str) -> str:
    """
    Format a tracking URL pattern with the given tracking number.
    Handles placeholders ({awb}, {tracking_number}), trailing '=', '/', '?',
    existing query params, or clean append.
    """
    clean_tn = str(tracking_number).strip() if tracking_number else ''
    if not pattern or not str(pattern).strip():
        return clean_tn if clean_tn.startswith(('http://', 'https://')) else ''
        
    url = str(pattern).strip()
    
    # If no tracking number, return base URL pattern or cleaned url
    if not clean_tn:
        return url

    # 1. Standard placeholders
    if '{tracking_number}' in url or '{awb}' in url:
        return url.replace('{tracking_number}', clean_tn).replace('{awb}', clean_tn)

    # 2. If the tracking number is already present in the URL, don't duplicate
    if clean_tn in url:
        return url

    # 3. If URL ends with an assignment, query delimiter, or path separator
    if url.endswith(('=', '/', '?')):
        return url + clean_tn

    # 4. If URL has query parameters
    if '?' in url:
        return f"{url}&awb={clean_tn}"

    # 5. Normal URL path
    if url.startswith(('http://', 'https://')):
        return f"{url.rstrip('/')}/?awb={clean_tn}"

    return url


def generate_tracking_url(courier_partner, tracking_number, custom_url=None):
    """Generate live official tracking URL for a given courier and tracking ID."""
    clean_tn = str(tracking_number).strip() if tracking_number else ''

    if custom_url and custom_url.strip():
        return format_tracking_url(custom_url.strip(), clean_tn)

    if not clean_tn:
        return ''

    code = normalize_courier_code(courier_partner)
    if code in COURIER_PARTNERS:
        meta = COURIER_PARTNERS[code]
        return format_tracking_url(meta['url_pattern'], clean_tn)

    # Check custom couriers
    custom_list = get_custom_couriers_from_db()
    for cc in custom_list:
        if cc['code'].lower() == str(code).lower() or cc['name'].lower() == str(courier_partner).lower():
            pat = cc.get('url_pattern') or ''
            if pat:
                return format_tracking_url(pat, clean_tn)

    if clean_tn.startswith(('http://', 'https://')):
        return clean_tn

    return ''


def get_courier_list():
    """Return ordered list of supported couriers for UI dropdowns, including custom couriers from DB."""
    list_items = [
        {
            'id': None,
            'code': key,
            'name': val['name'],
            'sample_format': val['sample_format'],
            'color': val['color'],
            'url_pattern': val['url_pattern'],
            'is_custom': (key == 'custom'),
            'is_db_custom': False
        }
        for key, val in COURIER_PARTNERS.items()
    ]

    custom_list = get_custom_couriers_from_db()
    for cc in custom_list:
        if not any(item['code'] == cc['code'] for item in list_items):
            list_items.append({
                'id': cc.get('id'),
                'code': cc['code'],
                'name': cc['name'],
                'sample_format': cc.get('sample_format') or 'Enter tracking number',
                'color': cc.get('color') or '#16a34a',
                'url_pattern': cc.get('url_pattern') or '{tracking_number}',
                'is_custom': True,
                'is_db_custom': True
            })

    return list_items
