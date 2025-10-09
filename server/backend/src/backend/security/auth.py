from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException, status
from starlette.responses import Response

from .crypto import encrypt_text, decrypt_text

SESSION_COOKIE_NAME = "wl_session"
# WL_ADMIN_PASSWORD = "WL_ADMIN_PASSWORD"
# 30 days default session lifetime
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30


@dataclass
class Session:
    exp: int
    iat: int

    def to_token(self) -> bytes:
        return encrypt_text(json.dumps({"exp": self.exp, "iat": self.iat})) or b""

    @staticmethod
    def from_token(token: str | bytes | None) -> Optional["Session"]:
        raw = decrypt_text(token)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return Session(exp=int(payload["exp"]), iat=int(payload["iat"]))
        except Exception:
            return None


def _now() -> int:
    return int(time.time())


def set_session_cookie(resp: Response, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    now = _now()
    sess = Session(exp=now + ttl_seconds, iat=now)
    token = sess.to_token().decode("utf-8")
    # Cookies: secure False by default (local dev). If BEHIND_HTTPS is set, mark secure.
    secure = os.environ.get("BEHIND_HTTPS", "0").lower() in ("1", "true", "yes")
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl_seconds,
        expires=ttl_seconds,
        secure=secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")


def has_valid_local_session(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    sess = Session.from_token(token)
    if not sess:
        return False
    return sess.exp > _now()


# oauth2-proxy middleware-mode headers:
# - X-Auth-Request-User, X-Auth-Request-Email, X-Forwarded-User
# - Authorization: Bearer <id/jwt token>
OAUTH_HEADER_CANDIDATES = (
    "X-Auth-Request-User",
    "X-Forwarded-User",
    "X-Auth-Request-Email",
    "Authorization",
)


def has_oauth2_proxy_headers(request: Request) -> bool:
    headers = request.headers
    for h in OAUTH_HEADER_CANDIDATES:
        if headers.get(h):
            return True
    return False


def is_authenticated(request: Request) -> bool:
    # Prioritize oauth2-proxy headers if present (deployed with Nginx middleware-mode)
    if has_oauth2_proxy_headers(request):
        return True
    # fallback to local password session
    return has_valid_local_session(request)


def require_auth(request: Request):
    if is_authenticated(request):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def verify_admin_password(password: str) -> bool:

    expected = os.environ.get("WL_ADMIN_PASSWORD", False)
    if isinstance(expected, bool) and not expected:
        return True

    return bool(expected) and (password == expected)