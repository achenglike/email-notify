import os
import hmac
from functools import wraps

from flask import request, jsonify


def _get_expected_token() -> str:
    token = os.environ.get("API_KEY", "").strip()
    if not token:
        raise RuntimeError("missing required env var: API_KEY")
    return token


def require_api_key(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()

        if not token or not hmac.compare_digest(token, _get_expected_token()):
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapper
