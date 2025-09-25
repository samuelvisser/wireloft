from __future__ import annotations

import requests
from typing import Any, Dict

from .config import DeviceAuthConfig


def start_device_flow(cfg: DeviceAuthConfig) -> Dict[str, Any]:
    """Start the OAuth 2.0 Device Authorization Grant with Auth0.

    Returns the raw response JSON which typically contains:
    - device_code
    - user_code
    - verification_uri
    - verification_uri_complete (if supported)
    - expires_in
    - interval
    """
    url = f"{cfg.issuer}/oauth/device/code"
    data = {
        "client_id": cfg.client_id,
        "audience": cfg.audience,
        "scope": cfg.scope,
    }
    r = requests.post(url, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def generate_login_info(cfg: DeviceAuthConfig) -> Dict[str, Any]:
    """Helper that returns a standardized dict with login URL and helpers.

    Keys:
    - url: A URL the user can click/open to complete authentication.
    - user_code: The user code to display if needed.
    - verification_uri: Original verification_uri from the provider (optional).
    - verification_uri_complete: Original verification_uri_complete if provided.
    - device_code, expires_in, interval: Raw flow parameters.
    """
    info = start_device_flow(cfg)
    url = info.get("verification_uri_complete") or info.get("verification_uri")
    return {
        "url": url,
        "user_code": info.get("user_code"),
        "verification_uri": info.get("verification_uri"),
        "verification_uri_complete": info.get("verification_uri_complete"),
        "device_code": info.get("device_code"),
        "expires_in": info.get("expires_in"),
        "interval": info.get("interval", 5),
        # include full payload for extensibility
        "_raw": info,
    }


def generate_login_url(cfg: DeviceAuthConfig) -> str:
    """Return only the URL to visit for login (may include user_code embedded)."""
    info = start_device_flow(cfg)
    return info.get("verification_uri_complete") or info.get("verification_uri")
