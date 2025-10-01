from __future__ import annotations

import time
import requests
from typing import Any, Dict

from .config import DeviceAuthConfig, DEFAULT_ISSUER


def start_device_flow(cfg: DeviceAuthConfig) -> Dict[str, Any]:
    """Start the OAuth 2.0 Device Authorization Grant with Auth0.

    Returns the raw response JSON which typically contains:
    - device_code
    - user_code
    - verification_uri
    - verification_uri_complete (if supported)
    - expires_in
    - interval

    Enriches the payload with:
    - _issuer_used: Which issuer domain was used for the request (helps for polling)
    """
    def _request(issuer: str) -> requests.Response:
        url = f"{issuer.rstrip('/')}/oauth/device/code"
        data = {
            "client_id": cfg.client_id,
            "audience": cfg.audience,
            "scope": cfg.scope,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        return requests.post(url, data=data, headers=headers, timeout=30)

    # First try the configured issuer
    r = _request(cfg.issuer)
    if r.status_code == 200:
        payload = r.json()
        payload.setdefault("_issuer_used", cfg.issuer.rstrip("/"))
        return payload

    # If the default issuer returns 404, try known alternatives automatically.
    if r.status_code == 404 and cfg.issuer.rstrip('/') == DEFAULT_ISSUER.rstrip('/'):
        for alt in ("https://dailywire.us.auth0.com", "https://dailywireplus.us.auth0.com"):
            r2 = _request(alt)
            if r2.status_code == 200:
                payload = r2.json()
                payload.setdefault("_issuer_used", alt.rstrip("/"))
                return payload

    # Otherwise raise the original error with a helpful hint
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(
            f"{e}. If this is a DailyWire tenant, try --issuer https://dailywire.us.auth0.com",
            response=r,
            request=r.request,
        ) from None

    payload = r.json()
    payload.setdefault("_issuer_used", cfg.issuer.rstrip("/"))
    return payload


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


def poll_for_tokens(
    cfg: DeviceAuthConfig,
    *,
    device_code: str,
    issuer: str,
    interval: int = 5,
) -> Dict[str, Any]:
    """Poll the token endpoint until the user authorizes or an error occurs.

    Returns the token response JSON on success, e.g. contains access_token, token_type,
    expires_in, and optionally refresh_token and id_token.
    """
    token_url = f"{issuer.rstrip('/')}/oauth/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": cfg.client_id,
    }
    wait = max(1, int(interval or 5))
    while True:
        r = requests.post(token_url, data=data, timeout=30)
        if r.status_code == 200:
            return r.json()
        try:
            err = r.json()
        except Exception:
            r.raise_for_status()
            continue
        code = (err or {}).get("error")
        if code in ("authorization_pending", "slow_down"):
            if code == "slow_down":
                # Back off per RFC 8628 recommendation
                wait = min(wait + 5, 60)
            time.sleep(wait)
            continue
        if code in ("expired_token", "access_denied", "invalid_request", "unsupported_grant_type"):
            raise RuntimeError(f"Device flow failed: {code}: {err}")
        # Unknown error; raise HTTP error with context
        r.raise_for_status()
