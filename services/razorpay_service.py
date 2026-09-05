import razorpay
from core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET


def get_razorpay_client():
    """Return an authenticated Razorpay client or None."""
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        try:
            return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        except Exception as e:
            print(f"[RAZORPAY] Initialization error: {str(e)}")
    return None
