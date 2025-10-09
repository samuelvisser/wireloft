"""
OAuth 2.0 Device Authorization Grant endpoints for DailyWire authentication.
Implements RFC 8628 compliant device flow using BFF (Backend-for-Frontend) pattern.

Access tokens are NEVER exposed to the frontend - they are stored in backend only.
The frontend can initiate and poll for authorization, but tokens remain server-side.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time

from dailywire_authorisation import DeviceAuthClient

router = APIRouter(prefix="/auth", tags=["DailyWire Auth"])

# Shared client instance
_client: Optional[DeviceAuthClient] = None

# In-memory storage for active device flows (device_code -> flow_data)
_active_flows: Dict[str, Dict[str, Any]] = {}


def get_client() -> DeviceAuthClient:
    """Get or create the shared DeviceAuthClient instance."""
    global _client
    if _client is None:
        from dailywire_authorisation import DeviceAuthConfig
        from dailywire_authorisation.config import get_default_config

        # Get config dict and convert to DeviceAuthConfig instance
        config_dict = get_default_config()
        config = DeviceAuthConfig(**config_dict)
        _client = DeviceAuthClient(config=config)
    return _client


# Request/Response Models
class DeviceAuthResponse(BaseModel):
    """Response from initiating device authorization flow."""
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: Optional[str] = None
    expires_in: int
    interval: int


class PollRequest(BaseModel):
    """Request to poll for authorization status."""
    device_code: str


class PollResponse(BaseModel):
    """Response from polling for authorization."""
    status: str  # "pending", "authorized", "expired", "denied", "slow_down"
    message: str


class StatusResponse(BaseModel):
    """Authentication status response."""
    authenticated: bool
    expires_at: Optional[float] = None


@router.post("/device", response_model=DeviceAuthResponse, status_code=status.HTTP_200_OK)
async def initiate_device_flow():
    """
    Initiate OAuth 2.0 Device Authorization Grant flow.

    Returns device_code, user_code, and verification_uri for the client to display.
    The user must visit verification_uri and enter the user_code to authorize.

    The device_code is used by the frontend to poll for authorization status.
    Tokens are NEVER exposed to the frontend - they remain stored server-side.

    Follows RFC 8628 Section 3.1-3.2.
    """
    try:
        client = get_client()
        flow_data = client.start_device_flow()

        # Track this flow temporarily (for cleanup of expired flows)
        _active_flows[flow_data["device_code"]] = {
            "created_at": time.time(),
            "expires_at": time.time() + flow_data["expires_in"]
        }

        return DeviceAuthResponse(**flow_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate device flow: {str(e)}"
        )


@router.post("/poll", response_model=PollResponse, status_code=status.HTTP_200_OK)
async def poll_for_authorization(request: PollRequest):
    """
    Poll for authorization status after user has been shown the device code.

    The client should poll this endpoint at the interval specified in the device flow response.
    Returns the authorization status without exposing any tokens.

    Possible status values:
    - "pending": User has not yet authorized
    - "authorized": User successfully authorized (tokens stored server-side)
    - "slow_down": Client is polling too quickly
    - "expired": Device code has expired
    - "denied": User denied authorization

    Follows RFC 8628 Section 3.4-3.5 but adapts to the BFF pattern.
    """
    try:
        # Check if this device code is being tracked
        flow = _active_flows.get(request.device_code)
        if flow and flow["expires_at"] < time.time():
            # Clean up expired flow
            _active_flows.pop(request.device_code, None)
            return PollResponse(
                status="expired",
                message="Device code has expired"
            )

        # Poll the OAuth provider
        client = get_client()
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": request.device_code,
            "client_id": client.config.client_id,
        }

        r = client.session.post(client.config.token_endpoint, data=data, timeout=30)

        if r.status_code == 200:
            token_data = r.json()

            from dailywire_authorisation.storage import TokenRecord
            expires_in = int(token_data.get("expires_in", 3600))
            expires_at = time.time() + expires_in - 30

            rec = TokenRecord(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
                expires_at=expires_at,
            )
            client.store.save(client._store_key, rec)

            # Clean up the flow tracking
            _active_flows.pop(request.device_code, None)

            return PollResponse(
                status="authorized",
                message="Authorization successful"
            )
        else:
            # Handle OAuth errors
            try:
                error_data = r.json()
                error_code = error_data.get("error", "unknown_error")
                error_desc = error_data.get("error_description", "")

                if error_code == "authorization_pending":
                    return PollResponse(
                        status="pending",
                        message="User has not yet authorized"
                    )
                elif error_code == "slow_down":
                    return PollResponse(
                        status="slow_down",
                        message="Polling too quickly, please slow down"
                    )
                elif error_code == "expired_token":
                    _active_flows.pop(request.device_code, None)
                    return PollResponse(
                        status="expired",
                        message="Device code has expired"
                    )
                elif error_code == "access_denied":
                    _active_flows.pop(request.device_code, None)
                    return PollResponse(
                        status="denied",
                        message="User denied authorization"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"OAuth error: {error_code} - {error_desc}"
                    )
            except ValueError:
                r.raise_for_status()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to parse OAuth response"
                )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Polling failed: {str(e)}"
        )


@router.get("/status", response_model=StatusResponse, status_code=status.HTTP_200_OK)
async def get_auth_status():
    """
    Check current authentication status.

    Returns whether valid tokens exist in the backend storage and when they expire.
    Does NOT expose any tokens to the frontend.
    """
    try:
        client = get_client()
        rec = client.store.load(client._store_key)

        if not rec:
            return StatusResponse(authenticated=False)

        # Check if token is still valid
        is_valid = rec.expires_at > time.time()

        return StatusResponse(
            authenticated=is_valid,
            expires_at=rec.expires_at if is_valid else None
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check auth status: {str(e)}"
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    """
    Logout the user by revoking and deleting stored tokens.

    This removes OAuth tokens from backend storage.
    """
    try:
        client = get_client()
        client.revoke()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )
