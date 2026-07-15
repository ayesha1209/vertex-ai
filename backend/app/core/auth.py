"""Cookie-based session auth. No JWT, no extra deps — stdlib only."""

import hashlib
import hmac
import os

from fastapi import HTTPException, Request, status

COOKIE_NAME = "vertex_session"


def _password() -> str:
    return os.getenv("AUTH_PASSWORD", "")


def _session_value() -> str:
    """A fixed HMAC that acts as the session cookie value. Changes only when AUTH_PASSWORD changes."""
    secret = _password() or "vertex-no-password-set"
    return hmac.new(secret.encode(), b"vertex-admin-session", hashlib.sha256).hexdigest()


def verify_password(password: str) -> bool:
    expected = _password()
    if not expected:
        return False
    return hmac.compare_digest(password.encode(), expected.encode())


def verify_session(cookie_value: str) -> bool:
    if not cookie_value:
        return False
    return hmac.compare_digest(cookie_value, _session_value())


def require_admin(request: Request) -> None:
    """Raise 401 if the session cookie is missing or invalid."""
    cookie = request.cookies.get(COOKIE_NAME, "")
    if not verify_session(cookie):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
