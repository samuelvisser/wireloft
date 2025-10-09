from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from backend.app import db_session
from backend.db.models.Settings import Settings
from backend.security.crypto import encrypt_text

from dailywire_authorisation.config import get_config
from dailywire_authorisation.device_flow import generate_login_info, poll_for_tokens

from backend.api.models.dailywire_auth import (
    DeviceStartResponse,
    DevicePollRequest,
    DevicePollResponse,
    AuthStatusResponse,
)

router = APIRouter()


@router.post("/device/start", response_model=DeviceStartResponse)
def device_start() -> DeviceStartResponse:
    """
    Start the OAuth 2.0 Device Authorization flow and return a user-friendly URL and user_code.
    Does not persist the device_code; clients should pass device_code to /device/poll.
    """
    cfg = get_config()
    info = generate_login_info(cfg)
    raw = info.get("_raw") or {}
    issuer_used = raw.get("_issuer_used") or cfg.issuer

    return DeviceStartResponse(
        url=info.get("url"),
        user_code=info.get("user_code"),
        device_code=info.get("device_code"),
        interval=int(info.get("interval") or 5),
        expires_in=int(info.get("expires_in") or 900),
        verification_uri=info.get("verification_uri"),
        verification_uri_complete=info.get("verification_uri_complete"),
        issuer=issuer_used,
    )


@router.post("/device/poll", response_model=DevicePollResponse)
def device_poll(body: DevicePollRequest) -> DevicePollResponse:
    """
    Poll the token endpoint until user has authorized. On success, securely store tokens.
    """
    cfg = get_config()
    try:
        token_resp = poll_for_tokens(
            cfg, device_code=body.device_code, issuer=body.issuer, interval=body.interval or 5
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    access_token = token_resp.get("access_token")
    refresh_token = token_resp.get("refresh_token")
    expires_in = int(token_resp.get("expires_in") or 3600)

    if not access_token:
        # Unexpected: success path without access_token
        raise HTTPException(status_code=502, detail="Token response missing access_token")

    # Persist tokens securely
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in)

    with db_session() as s:  # type: Session
        settings = s.query(Settings).first()
        if settings is None:
            settings = Settings()
            s.add(settings)
            s.flush()

        settings.auth_issuer = cfg.issuer
        settings.auth_audience = cfg.audience
        settings.auth_client_id = cfg.client_id
        settings.auth_scope = cfg.scope

        settings.encrypted_access_token = encrypt_text(access_token)
        settings.encrypted_refresh_token = encrypt_text(refresh_token) if refresh_token else None
        settings.token_expires_at = expires_at
        settings.last_auth_at = now
        settings.auth_status = "authenticated"
        s.flush()

    return DevicePollResponse(
        authenticated=True,
        status="authenticated",
        expires_at=expires_at,
        has_refresh_token=bool(refresh_token),
    )


@router.get("/device/status", response_model=AuthStatusResponse)
def device_status() -> AuthStatusResponse:
    """
    Check whether the server has stored tokens and if the access token is still valid.
    Does not return token values.
    """
    with db_session() as s:  # type: Session
        settings = s.query(Settings).first()
        if settings is None:
            return AuthStatusResponse(
                authenticated=False,
                status="not_configured",
                token_expires_at=None,
                has_refresh_token=False,
                last_auth_at=None,
            )

        now = datetime.now(timezone.utc)
        has_access = settings.encrypted_access_token is not None
        has_refresh = settings.encrypted_refresh_token is not None
        not_expired = settings.token_expires_at is not None and settings.token_expires_at > now

        authenticated = has_access and (not_expired or has_refresh)
        status = settings.auth_status or ("authenticated" if authenticated else "expired")

        return AuthStatusResponse(
            authenticated=authenticated,
            status=status,
            token_expires_at=settings.token_expires_at,
            has_refresh_token=has_refresh,
            last_auth_at=settings.last_auth_at,
        )
