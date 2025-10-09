from __future__ import annotations

import argparse
from typing import Optional

from .client import DeviceAuthClient
from .config import DeviceAuthConfig
from .storage import TokenStore

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="dailywire-auth", description="Generate a DailyWire Auth0 Device Authorization login URL")
    p.add_argument("--issuer", default=DeviceAuthConfig.issuer, help=f"Auth0 issuer domain (default: {DeviceAuthConfig.issuer})", )
    p.add_argument( "--client-id", default=DeviceAuthConfig.client_id, dest="client_id", help="Auth0 application client ID (default provided)",)
    p.add_argument(  "--scope", default=DeviceAuthConfig.scope, help=f"OAuth scope string (default: '{DeviceAuthConfig.scope}')", )
    p.add_argument( "--audience", default=DeviceAuthConfig.audience, help=f"API audience identifier (default: {DeviceAuthConfig.audience})",)

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Run device flow and save tokens")
    sub.add_parser("token", help="Print a valid access token (refresh if needed)")
    sub.add_parser("logout", help="Delete stored tokens")
    sub.add_parser("status", help="Show token status (expiry, presence)")

    return p.parse_args(argv)


def _get_config(ns) -> DeviceAuthConfig:
    return DeviceAuthConfig(
        issuer=ns.issuer,
        client_id=ns.client_id,
        scope=ns.scope,
        audience=ns.audience,
    )


def run_cli():
    args = _parse_args()
    cfg = _get_config(args)
    store = TokenStore()
    client = DeviceAuthClient(cfg, store=store)


    if args.cmd == "login":
        tokens = client.ensure_token()
        print("Authorized. Expires at:", int(tokens.expires_at))
    elif args.cmd == "token":
        tokens = client.ensure_token()
        print(tokens.access_token)
    elif args.cmd == "logout":
        client.revoke()
        print("Tokens deleted.")
    elif args.cmd == "status":
        rec = store.load(client.make_store_key())
        if not rec:
            print("No tokens stored.")
        else:
            import time
            ttl = int(rec.expires_at - time.time())
            print(f"Token present. TTL ~ {ttl} seconds. Refresh token: {'yes' if rec.refresh_token else 'no'}")
