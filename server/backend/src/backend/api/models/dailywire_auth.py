from typing import Optional

from backend.api.models.base import ResponseBase, RequestBase


# Request/Response Models
class DeviceAuthResponse(ResponseBase):
    """Response from initiating device authorization flow."""
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: Optional[str] = None
    expires_in: int
    interval: int


class TokenRequest(RequestBase):
    """Request to poll for access token."""
    device_code: str


class TokenResponse(ResponseBase):
    """OAuth token response."""
    access_token: str
    token_type: str
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class StatusResponse(ResponseBase):
    """Authentication status response."""
    authenticated: bool
    expires_at: Optional[float] = None