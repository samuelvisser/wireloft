from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.api.models.base import RequestBase, ResponseBase


class DeviceStartResponse(ResponseBase):
    url: str
    user_code: Optional[str] = None
    device_code: str
    interval: int
    expires_in: int
    verification_uri: Optional[str] = None
    verification_uri_complete: Optional[str] = None
    issuer: str


class DevicePollRequest(RequestBase):
    device_code: str
    issuer: str
    interval: Optional[int] = None


class DevicePollResponse(ResponseBase):
    authenticated: bool
    status: str
    expires_at: Optional[datetime] = None
    has_refresh_token: bool = False


class AuthStatusResponse(ResponseBase):
    authenticated: bool
    status: str
    token_expires_at: Optional[datetime] = None
    has_refresh_token: bool = False
    last_auth_at: Optional[datetime] = None
