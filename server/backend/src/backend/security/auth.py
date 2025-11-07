from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException, status
from starlette.responses import Response

from wireloft_config import get_settings
from wireloft_config.security.admin_auth import AdminAuth
from .crypto import encrypt_text, decrypt_text

SESSION_COOKIE_NAME = "wl_session"

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


def set_session_cookie(resp: Response, ttl_seconds: int = get_settings().login_session.ttl_seconds) -> None:
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
    # Fake valid session if admin auth is disabled
    if not AdminAuth().is_enabled:
        return True

    # Check if the session cookie is set
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    sess = Session.from_token(token)
    if not sess:
        return False
    return sess.exp > _now()


def is_authenticated(request: Request) -> bool:
    return has_valid_local_session(request)


def require_auth(request: Request) -> None:
    if is_authenticated(request):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def verify_admin_password_hash(password_hash: str) -> bool:
    return AdminAuth().verify(password_hash)