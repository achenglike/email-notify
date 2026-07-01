import os
import hmac


def get_expected_token() -> str:
    token = os.environ.get("API_KEY", "").strip()
    if not token:
        raise RuntimeError("missing required env var: API_KEY")
    return token


def is_authorized(auth_header: str) -> bool:
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header[len("Bearer "):].strip()
    if not token:
        return False
    return hmac.compare_digest(token, get_expected_token())
