"""Auth routes: login/logout/check via HTTP-only session cookie."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core.auth import COOKIE_NAME, _session_value, verify_password, verify_session

router = APIRouter()

_COOKIE_MAX_AGE = 86400 * 7  # 7 days


class LoginRequest(BaseModel):
    password: str


@router.post("/api/auth/login")
async def login(payload: LoginRequest, response: Response) -> dict:
    """Verify password and set a session cookie."""
    if not payload.password or not payload.password.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password required")
    if not verify_password(payload.password.strip()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    response.set_cookie(
        key=COOKIE_NAME,
        value=_session_value(),
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,   # internal tool — no HTTPS required
        path="/",
    )
    return {"ok": True}


@router.post("/api/auth/logout")
async def logout(response: Response) -> dict:
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/api/auth/check")
async def check(request: Request) -> dict:
    """Return whether the current request has a valid session cookie."""
    cookie = request.cookies.get(COOKIE_NAME, "")
    return {"authenticated": verify_session(cookie)}
