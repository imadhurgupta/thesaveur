from datetime import datetime
from flask import Blueprint, request, jsonify

api_webhooks_bp = Blueprint('api_webhooks_bp', __name__)


@api_webhooks_bp.route('/api/webhooks/health', methods=['GET'], endpoint='webhook_health')
def webhook_health():
    """Generic webhook endpoint health check."""
    return jsonify({
        'status': 'active',
        'service': 'The Saveur Webhook Handler',
        'timestamp': datetime.now().isoformat()
    }), 200
