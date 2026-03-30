from functools import wraps

from flask import jsonify, request


def _extract_api_key() -> str | None:
    header_key = request.headers.get("X-API-Key")
    if header_key:
        return header_key.strip()

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return None


def require_api_key(expected_key: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            supplied = _extract_api_key()
            if supplied != expected_key:
                return jsonify({"error": "unauthorized"}), 401
            return func(*args, **kwargs)

        return wrapper

    return decorator
