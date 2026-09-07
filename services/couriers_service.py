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
    'shipglobal': {
        'name': 'ShipGlobal',
        'code': 'shipglobal',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#0066CC',
        'bg_color': 'rgba(0, 102, 204, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. SGI123456789 / AWB (ShipGlobal Tracking No)'
    },
    'dhlecs-classic': {
        'name': 'DHL E-Commerce',
        'code': 'DHLECS-CLASSIC',
        'service_code': 'DHLECS-CLASSIC',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#D40511',
        'bg_color': 'rgba(212, 5, 17, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. UUS000000 / AWB'
    },
    'dpd-classic': {
        'name': 'DPD',
        'code': 'DPD-CLASSIC',
        'service_code': 'DPD-CLASSIC',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#DC0032',
        'bg_color': 'rgba(220, 0, 50, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. DPD000000 / AWB'
    },
    'uniuni-classic': {
        'name': 'UniUni',
        'code': 'UNIUNI-CLASSIC',
        'service_code': 'UNIUNI-CLASSIC',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#00A862',
        'bg_color': 'rgba(0, 168, 98, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. UUN000000 / AWB'
    },
    'vipparcel-classic': {
        'name': 'VipParcel',
        'code': 'VIPPARCEL-CLASSIC',
        'service_code': 'VIPPARCEL-CLASSIC',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#6366F1',
        'bg_color': 'rgba(99, 102, 241, 0.08)',
        'icon_type': 'package',
        'sample_format': 'e.g. VIP000000 / AWB'
    },
    'ubi-classic': {
        'name': 'UBI (eTower)',
        'code': 'UBI-CLASSIC',
        'service_code': 'UBI-CLASSIC',
        'provider': 'ShipGlobal',
        'url_pattern': 'https://www.shipglobal.in/tracking/?tracking_no={tracking_number}',
        'color': '#0284C7',
        'bg_color': 'rgba(2, 132, 199, 0.08)',
        'icon_type': 'truck',
        'sample_format': 'e.g. UBI000000 / AWB'
    },
    'custom': {
        'name': 'Local / Custom Courier',
        'code': 'custom',
        'provider': 'Direct',
        'url_pattern': '{tracking_number}',
        'color': '#16A34A',
        'bg_color': 'rgba(22, 163, 74, 0.08)',
        'icon_type': 'package',
        'sample_format': 'Enter Tracking Number or Website URL'
    }
}

# ── Hierarchical Logistics Model: Provider -> Carriers ───────────────────────
LOGISTICS_PROVIDERS = [
    {
        'id': 'shipglobal',
        'name': 'ShipGlobal',
        'badge': 'Cross-Border Aggregator',
        'tag': '1-Click Official Labels',
        'color': '#0066CC',
        'bg_color': 'rgba(0, 102, 204, 0.08)',
        'description': 'Cross-border logistics aggregator. Generates PDF shipping labels & AWB directly via API.',
        'carriers': [
            {'code': 'DHLECS-CLASSIC', 'name': 'DHL E-Commerce (DHLECS-CLASSIC)', 'carrier_name': 'DHL E-Commerce', 'provider': 'shipglobal', 'format': 'e.g. UUS000000'},
            {'code': 'DPD-CLASSIC', 'name': 'DPD (DPD-CLASSIC)', 'carrier_name': 'DPD', 'provider': 'shipglobal', 'format': 'e.g. DPD000000'},
            {'code': 'UNIUNI-CLASSIC', 'name': 'UniUni (UNIUNI-CLASSIC)', 'carrier_name': 'UniUni', 'provider': 'shipglobal', 'format': 'e.g. UUN000000'},
            {'code': 'VIPPARCEL-CLASSIC', 'name': 'VipParcel (VIPPARCEL-CLASSIC)', 'carrier_name': 'VipParcel', 'provider': 'shipglobal', 'format': 'e.g. VIP000000'},
            {'code': 'UBI-CLASSIC', 'name': 'UBI eTower (UBI-CLASSIC)', 'carrier_name': 'UBI (eTower)', 'provider': 'shipglobal', 'format': 'e.g. UBI000000'},
        ]
    },
    {
        'id': 'shiprocket',
        'name': 'Shiprocket',
        'badge': 'Domestic Multi-Carrier Aggregator',
        'tag': 'Unified Automated Tracking',
        'color': '#E67E22',
        'bg_color': 'rgba(230, 126, 34, 0.08)',
        'description': 'Domestic logistics aggregator. Provides multi-carrier shipping & unified automated tracking.',
        'carriers': [
            {'code': 'bluedart', 'name': 'Blue Dart (via Shiprocket)', 'carrier_name': 'Blue Dart', 'provider': 'shiprocket', 'format': 'e.g. 89234567890'},
            {'code': 'delhivery', 'name': 'Delhivery (via Shiprocket)', 'carrier_name': 'Delhivery', 'provider': 'shiprocket', 'format': 'e.g. 1401234567890'},
            {'code': 'dtdc', 'name': 'DTDC (via Shiprocket)', 'carrier_name': 'DTDC', 'provider': 'shiprocket', 'format': 'e.g. D12345678'},
            {'code': 'xpressbees', 'name': 'Xpressbees (via Shiprocket)', 'carrier_name': 'Xpressbees', 'provider': 'shiprocket', 'format': 'e.g. 138123456789'},
            {'code': 'shadowfax', 'name': 'Shadowfax (via Shiprocket)', 'carrier_name': 'Shadowfax', 'provider': 'shiprocket', 'format': 'e.g. SF123456789'},
            {'code': 'ekart', 'name': 'Ekart Logistics (via Shiprocket)', 'carrier_name': 'Ekart Logistics', 'provider': 'shiprocket', 'format': 'e.g. FMPC1234567890'},
            {'code': 'indiapost', 'name': 'India Post (via Shiprocket)', 'carrier_name': 'India Post', 'provider': 'shiprocket', 'format': 'e.g. EM123456789IN'},
            {'code': 'fedex', 'name': 'FedEx India (via Shiprocket)', 'carrier_name': 'FedEx', 'provider': 'shiprocket', 'format': 'e.g. 794812345678'},
            {'code': 'dhl', 'name': 'DHL Express (via Shiprocket)', 'carrier_name': 'DHL Express', 'provider': 'shiprocket', 'format': 'e.g. 1234567890'},
        ]
    },
    {
        'id': 'direct',
        'name': 'Direct Carriers & Custom',
        'badge': 'Direct Carrier Account',
        'tag': 'Direct / Offline Partner',
        'color': '#16A34A',
        'bg_color': 'rgba(22, 163, 74, 0.08)',
        'description': 'Direct contract with courier or offline local delivery partners.',
        'carriers': [
            {'code': 'delhivery', 'name': 'Delhivery Direct API', 'carrier_name': 'Delhivery', 'provider': 'direct', 'format': 'e.g. 1401234567890'},
            {'code': 'amazon', 'name': 'Amazon Shipping (ATS)', 'carrier_name': 'Amazon Shipping', 'provider': 'direct', 'format': 'e.g. TBA1234567890'},
            {'code': 'custom', 'name': 'Local / Custom Transport Partner', 'carrier_name': 'Custom Courier', 'provider': 'direct', 'format': 'Enter Tracking Number or Website URL'},
        ]
    }
]


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
    
    if 'dhlecs' in key or 'dhlecommerce' in key:
        return 'dhlecs-classic'
    elif 'dpd' in key:
        return 'dpd-classic'
    elif 'uniuni' in key:
        return 'uniuni-classic'
    elif 'vipparcel' in key:
        return 'vipparcel-classic'
    elif 'ubi' in key or 'etower' in key:
        return 'ubi-classic'
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
    elif 'shipglobal' in key or 'ship_global' in key or 'shipglob' in key:
        return 'shipglobal'
    return courier_partner.strip()


def get_logistics_providers():
    """Return the complete hierarchical list of Providers -> Carriers."""
    import copy
    providers = copy.deepcopy(LOGISTICS_PROVIDERS)
    custom_list = get_custom_couriers_from_db()
    for cc in custom_list:
        providers[2]['carriers'].append({
            'code': cc['code'],
            'name': f"{cc['name']} (Custom)",
            'carrier_name': cc['name'],
            'provider': 'direct',
            'format': cc.get('sample_format') or 'Enter Tracking Number',
            'is_custom': True
        })
    return providers


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


def generate_tracking_url(courier_partner, tracking_number, custom_url=None):
    """Generate live official tracking URL for a given courier and tracking ID."""
    clean_tn = str(tracking_number).strip() if tracking_number else ''

    if custom_url and custom_url.strip():
        url_pat = custom_url.strip()
        if '{tracking_number}' in url_pat or '{awb}' in url_pat:
            return url_pat.replace('{tracking_number}', clean_tn).replace('{awb}', clean_tn)
        if url_pat.startswith(('http://', 'https://')):
            return url_pat

    if not clean_tn:
        return ''

    code = normalize_courier_code(courier_partner)
    if code in COURIER_PARTNERS:
        meta = COURIER_PARTNERS[code]
        pat = meta['url_pattern']
        if '{tracking_number}' in pat or '{awb}' in pat:
            return pat.replace('{tracking_number}', clean_tn).replace('{awb}', clean_tn)
        return pat

    # Check custom couriers
    custom_list = get_custom_couriers_from_db()
    for cc in custom_list:
        if cc['code'].lower() == str(code).lower() or cc['name'].lower() == str(courier_partner).lower():
            pat = cc.get('url_pattern') or ''
            if pat:
                if '{tracking_number}' in pat or '{awb}' in pat:
                    return pat.replace('{tracking_number}', clean_tn).replace('{awb}', clean_tn)
                return pat

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
