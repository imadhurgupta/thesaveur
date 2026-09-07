import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import base64
from app import app
from database import get_db
from services.tracking_service import (
    save_system_setting,
    get_system_setting,
    get_shipglobal_auth_token,
    create_shipglobal_shipment
)

def run_tests():
    print("=== Testing ShipGlobal 401 Fix and Sandbox Simulation ===")
    
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 'USR-ADMIN'
            sess['is_admin'] = True

        # 1. Test test-auth with sandbox=True
        print("\n1. Testing test-auth route with sandbox=True:")
        res = client.post('/admin/settings/shipglobal/test-auth', json={'sandbox': True})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.get_json()
        print("Response:", data)
        assert data.get('success') is True, "Sandbox auth should succeed"
        assert data.get('sandbox') is True

        # 2. Test test-auth with live credentials returning 401
        print("\n2. Testing test-auth route with unprovisioned live credentials:")
        res = client.post('/admin/settings/shipglobal/test-auth', json={
            'email': 'albertmassey99@gmail.com',
            'password': 'test_wrong_password',
            'sandbox': False
        })
        assert res.status_code == 200
        data = res.get_json()
        print("Response:", data)
        assert data.get('success') is False
        assert data.get('can_sandbox') is True
        assert 'Sandbox' in data.get('error', '')
        print("Actionable 401 diagnostic verified!")

        # 3. Enable Sandbox Mode and test order label generation
        print("\n3. Testing Sandbox Label Generation on real DB order:")
        save_system_setting('SHIPGLOBAL_SANDBOX_MODE', '1')
        save_system_setting('SHIPGLOBAL_DEFAULT_SERVICE', 'CIRRO-CLASSIC')

        # Find an existing order to test
        db = get_db()
        order = db.execute("SELECT id, order_number FROM orders ORDER BY id DESC LIMIT 1").fetchone()
        assert order is not None, "Need at least 1 order in database"
        order_id = order['id']
        order_ref = order['order_number'] or str(order_id)
        print(f"Testing on Order ID {order_id} (Ref: {order_ref})")

        # Test create_shipglobal_shipment
        result = create_shipglobal_shipment(order_id, service_code='CIRRO-CLASSIC')
        print("create_shipglobal_shipment result:", {k: v for k, v in result.items() if k != 'pdf_base64'})
        assert result.get('success') is True
        assert result.get('sandbox') is True
        assert result.get('waybill_number').startswith('CIR')
        assert len(result.get('pdf_base64', '')) > 1000

        # Verify PDF can be decoded
        pdf_bytes = base64.b64decode(result['pdf_base64'])
        assert pdf_bytes.startswith(b'%PDF'), "Decoded data must be a valid PDF file"
        print(f"Verified valid PDF! Length: {len(pdf_bytes)} bytes")

        # Verify DB order record
        db = get_db()
        updated_order = db.execute("SELECT courier_partner, tracking_number, status, shipping_label_pdf FROM orders WHERE id = ?", (order_id,)).fetchone()
        assert updated_order['courier_partner'] == 'shipglobal'
        assert updated_order['tracking_number'] == result['waybill_number']
        assert updated_order['status'] == 'Shipped'
        print("DB order verified: Status='Shipped', courier_partner='shipglobal', tracking_number=", updated_order['tracking_number'])

        # 4. Test downloading the label PDF via admin endpoint
        print("\n4. Testing /admin/orders/<ref>/download-shipping-label endpoint:")
        dl_res = client.get(f"/admin/orders/{order_ref}/download-shipping-label")
        print("Download status:", dl_res.status_code, "headers:", dl_res.headers)
        assert dl_res.status_code == 200, f"Expected 200, got {dl_res.status_code}"
        assert dl_res.headers.get('Content-Type') == 'application/pdf'
        assert dl_res.data.startswith(b'%PDF'), "Downloaded content must be PDF"
        print("Downloaded bytes length:", len(dl_res.data))
        print("Download endpoint returned full binary PDF successfully!")

        print("\nALL VERIFICATIONS PASSED!")

if __name__ == "__main__":
    run_tests()
