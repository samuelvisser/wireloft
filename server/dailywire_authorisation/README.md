# dailywire-authorisation

A small helper package to generate a login URL for DailyWire using the OAuth 2.0 Device Authorization Grant (Auth0).

This mirrors the behavior of the .NET project which uses Auth0's Device Code flow to authenticate, but focuses solely on generating the login URL and user code so a user can authenticate in the browser.

## Installation (within this workspace)
This repo uses a uv workspace. The package is already included in the root `pyproject.toml` under `members`.

## Usage
You can run the CLI to get the login URL and (optionally) the user code:

```
# Quick start (uses built-in defaults)
uv run dailywire-auth
# Or JSON output
uv run dailywire-auth --json

# Override via env vars (optional)
export DAILYWIRE_OAUTH_ISSUER="https://<your-auth0-tenant>.auth0.com"
export DAILYWIRE_OAUTH_AUDIENCE="<api-audience>"
export DAILYWIRE_OAUTH_CLIENT_ID="<client-id>"
export DAILYWIRE_OAUTH_SCOPE="openid profile email offline_access"
uv run dailywire-auth
```

Alternatively, pass values via flags:
```
uv run dailywire-auth \
  --issuer "https://<your-auth0-tenant>.auth0.com" \
  --audience "<api-audience>" \
  --client-id "<client-id>" \
  --scope "openid profile email offline_access"
```

Sample JSON output:
```json
{
  "url": "https://auth0-tenant/oauth/device?user_code=ABCD-EFGH",
  "user_code": "ABCD-EFGH",
  "verification_uri": "https://auth0-tenant/activate",
  "verification_uri_complete": "https://auth0-tenant/activate?user_code=ABCD-EFGH",
  "device_code": "...",
  "expires_in": 900,
  "interval": 5,
  "_raw": { "...": "provider response" }
}
```

## Library usage
```python
from dailywire_authorisation import get_config, generate_login_info

cfg = get_config()  # pulls from env vars or built-in defaults
info = generate_login_info(cfg)
print("Visit:", info["url"])       # A browser URL for the user
print("User code:", info["user_code"])  # Show if not embedded in URL
```

## Configuration
- DAILYWIRE_OAUTH_ISSUER or OAUTH_ISSUER: Auth0 issuer base URL (including https://)
- DAILYWIRE_OAUTH_AUDIENCE or OAUTH_AUDIENCE: API audience identifier
- DAILYWIRE_OAUTH_CLIENT_ID or OAUTH_CLIENT_ID: Auth0 app client ID
- DAILYWIRE_OAUTH_SCOPE or OAUTH_SCOPE: OAuth scope string (default: "openid profile email offline_access")

### Defaults
These are used when you don't provide CLI flags or env vars:
- issuer: https://dailywireplus.auth0.com
- audience: https://api.dailywire.com
- client_id: FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE
- scope: openid profile email offline_access

Note: These defaults are based on publicly observed configurations and may change. If login fails for your tenant, supply the correct values via flags or env vars.
