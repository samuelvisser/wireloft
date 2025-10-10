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


class PollRequest(RequestBase):
    """Request to poll for authorization status."""
    device_code: str


class PollResponse(ResponseBase):
    """Response from polling for authorization."""
    status: str  # "authorized", "expired", "denied"
    message: str


class StatusResponse(ResponseBase):
    """Authentication status response."""
    authenticated: bool
    contains_refresh_token: bool
    expires_at: Optional[float] = None
