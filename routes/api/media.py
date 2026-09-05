import requests
from flask import Blueprint, request, jsonify
from services.auth_service import admin_required

api_media_bp = Blueprint('api_media_bp', __name__)


@api_media_bp.route('/api/resolve-onedrive', methods=['POST'], endpoint='api_resolve_onedrive')
@admin_required
def api_resolve_onedrive():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # If it's a short URL (1drv.ms), resolve the redirect first
        if "1drv.ms" in url:
            response = requests.get(url, allow_redirects=True, timeout=10)
            final_url = response.url
        else:
            final_url = url

        # Convert redir link to embed link
        if "onedrive.live.com/redir" in final_url:
            final_url = final_url.replace("onedrive.live.com/redir", "onedrive.live.com/embed")
        elif "onedrive.live.com/redir.aspx" in final_url:
            final_url = final_url.replace("onedrive.live.com/redir.aspx", "onedrive.live.com/embed.aspx")

        return jsonify({'success': True, 'resolved_url': final_url})
    except Exception as e:
        return jsonify({'error': f'Failed to resolve URL: {str(e)}'}), 500
