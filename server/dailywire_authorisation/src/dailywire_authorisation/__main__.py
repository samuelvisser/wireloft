from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .config import (
    get_config,
    DEFAULT_ISSUER,
    DEFAULT_AUDIENCE,
    DEFAULT_CLIENT_ID,
    DEFAULT_SCOPE,
)
from .device_flow import generate_login_info, poll_for_tokens


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dailywire-auth", description="Generate a DailyWire Auth0 Device Authorization login URL")
    parser.add_argument("--json",action="store_true", help="Output full JSON (url, user_code, device_code, interval, expires_in)",)
    parser.add_argument("--issuer",default=DEFAULT_ISSUER,help=f"Auth0 issuer domain (default: {DEFAULT_ISSUER})", )
    parser.add_argument( "--audience", default=DEFAULT_AUDIENCE,help=f"API audience identifier (default: {DEFAULT_AUDIENCE})",)
    parser.add_argument( "--client-id", dest="client_id", default=DEFAULT_CLIENT_ID, help="Auth0 application client ID (default provided)",)
    parser.add_argument(  "--scope",  default=DEFAULT_SCOPE, help=f"OAuth scope string (default: '{DEFAULT_SCOPE}')", )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:

    args = _parse_args(argv)

    try:
        cfg = get_config(issuer=args.issuer, audience=args.audience, client_id=args.client_id, scope=args.scope)
        info = generate_login_info(cfg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Always show the login URL first
    print("Login URL:", info["url"])  # may already include user_code
    if info.get("user_code"):
        print("User code:", info["user_code"])  # display in case manual entry is needed

    # Determine which issuer to use for polling (respect auto-fallbacks)
    issuer_used = (info.get("_raw") or {}).get("_issuer_used") or cfg.issuer

    # Wait for the user to complete login in the browser, then retrieve tokens
    try:
        tokens = poll_for_tokens(
            cfg,
            device_code=info["device_code"],
            issuer=issuer_used,
            interval=int(info.get("interval", 5) or 5),
        )
    except KeyboardInterrupt:
        print("\nCancelled. You can re-run the command to start a new device flow.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error while waiting for authorization: {e}", file=sys.stderr)
        return 1

    if args.json:
        output = dict(info)
        output["tokens"] = tokens
        print(json.dumps(output, ensure_ascii=False))
    else:
        print("Authorization complete.")
        if tokens.get("access_token"):
            print("Access token:", tokens["access_token"])  # Authorization bearer token
        if tokens.get("refresh_token"):
            print("Refresh token:", tokens["refresh_token"])  # Use to refresh access
        if tokens.get("id_token"):
            print("ID token:", tokens["id_token"])  # Optional depending on scopes
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
