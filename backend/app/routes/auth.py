"""Auth routes: login/logout/check via HTTP-only session cookie."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.auth import COOKIE_NAME, _session_value, verify_password, verify_session

router = APIRouter()

_COOKIE_MAX_AGE = 86400 * 7  # 7 days


class LoginRequest(BaseModel):
    password: str


@router.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    """Verify password and set a session cookie."""
    if not payload.password or not payload.password.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password required")
    if not verify_password(payload.password.strip()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    # Cross-site (Vercel frontend -> Render backend) requires SameSite=None + Secure, which in
    # turn requires HTTPS. Locally the request scheme is http, so fall back to Lax/insecure so
    # login still works over plain http://localhost.
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=_session_value(),
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="none" if is_https else "lax",
        secure=is_https,
        path="/",
    )
    return {"ok": True}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict:
    """Clear the session cookie."""
    is_https = request.url.scheme == "https"
    response.delete_cookie(
        key=COOKIE_NAME, path="/", samesite="none" if is_https else "lax", secure=is_https
    )
    return {"ok": True}


@router.get("/api/auth/check")
async def check(request: Request) -> dict:
    """Return whether the current request has a valid session cookie."""
    cookie = request.cookies.get(COOKIE_NAME, "")
    return {"authenticated": verify_session(cookie)}
