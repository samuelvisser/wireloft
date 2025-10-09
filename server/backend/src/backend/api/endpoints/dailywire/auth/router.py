"""
OAuth 2.0 Device Authorization Grant endpoints for DailyWire authentication.
Implements RFC 8628 compliant device flow using BFF (Backend-for-Frontend) pattern.

Access tokens are NEVER exposed to the frontend - they are stored in backend only.
The frontend can initiate and poll for authorization, but tokens remain server-side.
"""
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any
import time

from backend.api.models.dailywire_auth import *
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

        # Track this flow temporarily (for cleanup and validation)
        _active_flows[flow_data["device_code"]] = {
            "created_at": time.time(),
            "expires_at": time.time() + flow_data["expires_in"],
            "interval": flow_data["interval"],
            "expires_in": flow_data["expires_in"]
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
    Complete the device authorization flow by polling until authorized.

    This endpoint blocks until the user authorizes (or denies/expires).
    The client should call this ONCE after displaying the device code.
    Tokens are stored server-side and NEVER exposed to the frontend.

    Possible status values:
    - "authorized": User successfully authorized (tokens stored server-side)
    - "expired": Device code expired before user authorized
    - "denied": User denied authorization

    Follows RFC 8628 Section 3.4-3.5 using the client's poll_until_authorized method.
    """
    try:
        # Get flow data if it exists
        flow = _active_flows.get(request.device_code)

        if not flow:
            # Flow not found - may have been used already or never existed
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device code not found. It may have expired or already been used."
            )

        # Check if flow has expired
        if flow["expires_at"] < time.time():
            _active_flows.pop(request.device_code, None)
            return PollResponse(
                status="expired",
                message="Device code has expired"
            )

        # Use the client's poll_until_authorized method
        # This will block until authorization completes (or fails)
        client = get_client()

        try:
            # Poll until authorized - the client automatically saves tokens
            client.poll_until_authorized(
                device_code=request.device_code,
                interval=flow.get("interval", 5),
                expires_in=int(flow["expires_at"] - time.time())
            )

            # Clean up the flow tracking
            _active_flows.pop(request.device_code, None)

            return PollResponse(
                status="authorized",
                message="Authorization successful"
            )

        except RuntimeError as e:
            # Handle errors from poll_until_authorized
            error_msg = str(e).lower()
            _active_flows.pop(request.device_code, None)

            if "expired" in error_msg:
                return PollResponse(
                    status="expired",
                    message="Device code expired before authorization"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )

        except PermissionError:
            # User denied the request
            _active_flows.pop(request.device_code, None)
            return PollResponse(
                status="denied",
                message="User denied authorization"
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
    Check the current authentication status.

    Returns whether valid tokens exist in the backend storage and when they expire.
    Does NOT expose any tokens to the frontend.
    """
    try:
        client = get_client()
        client_status = client.status()

        # Check if the token is still valid
        is_valid = client_status.expires_at > time.time()
        return StatusResponse(
            **client_status.__dict__,
            expires_at=client_status.expires_at if is_valid else None
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
