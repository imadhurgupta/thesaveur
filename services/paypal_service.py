import requests
from core.config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE, PAYPAL_EXCHANGE_RATE


def get_paypal_api_base():
    """Return the PayPal API base endpoint according to mode."""
    if PAYPAL_MODE == 'live':
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def get_paypal_access_token():
    """Fetch an OAuth2 access token from PayPal."""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return None
    try:
        url = f"{get_paypal_api_base()}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {
            "grant_type": "client_credentials"
        }
        res = requests.post(
            url,
            headers=headers,
            data=data,
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            timeout=10
        )
        if res.status_code == 200:
            return res.json().get('access_token')
        else:
            print(f"[PAYPAL] Failed to get access token: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[PAYPAL] OAuth error: {str(e)}")
    return None
