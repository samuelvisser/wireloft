from __future__ import annotations

import os
from dataclasses import dataclass


# These can be overridden via CLI flags or environment variables.
DEFAULT_ISSUER = "https://authorize.dailywire.com"
DEFAULT_AUDIENCE = "https://api.dailywire.com/"
DEFAULT_CLIENT_ID = "FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE"
DEFAULT_SCOPE = "openid profile offline_access"


@dataclass(frozen=True)
class DeviceAuthConfig:
    issuer: str
    audience: str
    client_id: str
    scope: str = DEFAULT_SCOPE


def get_config(
    *,
    issuer: str | None = None,
    audience: str | None = None,
    client_id: str | None = None,
    scope: str | None = None,
) -> DeviceAuthConfig:
    """Load device authorization config from parameters, environment, or defaults.

    Resolution order (highest precedence first):
    1) Explicit function arguments
    2) Environment variables (DAILYWIRE_* first, then generic OAUTH_*):
       - DAILYWIRE_OAUTH_ISSUER or OAUTH_ISSUER
       - DAILYWIRE_OAUTH_AUDIENCE or OAUTH_AUDIENCE
       - DAILYWIRE_OAUTH_CLIENT_ID or OAUTH_CLIENT_ID
       - DAILYWIRE_OAUTH_SCOPE or OAUTH_SCOPE
    3) Built-in reasonable defaults (see constants above)
    """
    iss = (
        issuer
        or os.getenv("DAILYWIRE_OAUTH_ISSUER")
        or os.getenv("OAUTH_ISSUER")
        or DEFAULT_ISSUER
    )
    aud = (
        audience
        or os.getenv("DAILYWIRE_OAUTH_AUDIENCE")
        or os.getenv("OAUTH_AUDIENCE")
        or DEFAULT_AUDIENCE
    )
    cid = (
        client_id
        or os.getenv("DAILYWIRE_OAUTH_CLIENT_ID")
        or os.getenv("OAUTH_CLIENT_ID")
        or DEFAULT_CLIENT_ID
    )
    scp = (
        scope
        or os.getenv("DAILYWIRE_OAUTH_SCOPE")
        or os.getenv("OAUTH_SCOPE")
        or DEFAULT_SCOPE
    )

    # Normalize issuer to not end with a trailing slash
    iss = iss.rstrip("/")

    return DeviceAuthConfig(issuer=iss, audience=aud, client_id=cid, scope=scp)
