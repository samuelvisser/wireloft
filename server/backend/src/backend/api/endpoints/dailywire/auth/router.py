"""
OAuth 2.0 Device Authorization Grant endpoints for DailyWire authentication.
Implements RFC 8628 compliant device flow.
"""
from fastapi import APIRouter, HTTPException, status

from backend.api.models.dailywire_auth import *
from dailywire_authorisation import DeviceAuthClient

router = APIRouter(prefix="/auth", tags=["DailyWire Auth"])

_client: Optional[DeviceAuthClient] = None

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


# Endpoints
@router.post("/device", response_model=DeviceAuthResponse, status_code=status.HTTP_200_OK)
async def initiate_device_flow():
    """
    Initiate OAuth 2.0 Device Authorization Grant flow.

    Returns device_code and user_code that the client should display to the user.
    The user must visit verification_uri and enter the user_code to authorize.

    Follows RFC 8628 Section 3.1-3.2.
    """
    try:
        client = get_client()
        flow_data = client.start_device_flow()
        return DeviceAuthResponse(**flow_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate device flow: {str(e)}"
        )


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def poll_for_token(request: TokenRequest):
    """
    Poll for access token after user authorization.

    The client should poll this endpoint at the interval specified in the device flow response.
    Returns 400 with 'authorization_pending' if user hasn't authorized yet.
    Returns 400 with 'slow_down' if client is polling too quickly.
    Returns 400 with 'expired_token' if device_code has expired.
    Returns 403 with 'access_denied' if user denied authorization.

    Follows RFC 8628 Section 3.4-3.5.
    """
    try:
        client = get_client()

        # We'll do a single poll check with minimal wait
        # The client is responsible for implementing the polling loop
        import time
        import requests

        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": request.device_code,
            "client_id": client.config.client_id,
        }

        r = client.session.post(client.config.token_endpoint, data=data, timeout=30)

        if r.status_code == 200:
            token_data = r.json()

            # Save token to store
            from dailywire_authorisation.storage import TokenRecord
            expires_in = int(token_data.get("expires_in", 3600))
            rec = TokenRecord(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
                expires_at=time.time() + expires_in - 30,
            )
            client.store.save(client._store_key, rec)

            return TokenResponse(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=expires_in,
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope")
            )
        else:
            try:
                error_data = r.json()
                error_code = error_data.get("error", "unknown_error")
                error_desc = error_data.get("error_description", "")

                if error_code == "authorization_pending":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": "authorization_pending", "error_description": "User has not yet authorized"}
                    )
                elif error_code == "slow_down":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": "slow_down", "error_description": "Client is polling too quickly"}
                    )
                elif error_code == "expired_token":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": "expired_token", "error_description": "The device_code has expired"}
                    )
                elif error_code == "access_denied":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={"error": "access_denied", "error_description": "User denied authorization"}
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"error": error_code, "error_description": error_desc}
                    )
            except ValueError:
                r.raise_for_status()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to parse token endpoint response"
                )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token polling failed: {str(e)}"
        )


@router.get("/status", response_model=StatusResponse, status_code=status.HTTP_200_OK)
async def get_auth_status():
    """
    Check current authentication status.

    Returns whether a valid token exists and when it expires.
    """
    try:
        client = get_client()
        rec = client.store.load(client._store_key)

        if not rec:
            return StatusResponse(authenticated=False)

        import time
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


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token():
    """
    Refresh the access token using the stored refresh token.

    Returns a new access token if refresh is successful.
    Returns 401 if no valid refresh token exists.
    """
    try:
        client = get_client()
        rec = client.store.load(client._store_key)

        if not rec or not rec.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token available"
            )

        refreshed = client._refresh(rec.refresh_token)

        if not refreshed:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed"
            )

        client.store.save(client._store_key, refreshed)

        import time
        expires_in = int(refreshed.expires_at - time.time())

        return TokenResponse(
            access_token=refreshed.access_token,
            token_type=refreshed.token_type,
            expires_in=expires_in,
            refresh_token=refreshed.refresh_token,
            scope=refreshed.scope
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.delete("/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token():
    """
    Revoke and delete the stored authentication tokens.

    This performs a local logout by removing tokens from storage.
    """
    try:
        client = get_client()
        client.revoke()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token revocation failed: {str(e)}"
        )
