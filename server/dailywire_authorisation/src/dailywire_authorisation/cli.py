from __future__ import annotations

import os
import argparse

from .client import DeviceAuthClient, DeviceAuthConfig
from .storage import TokenStore

def _config_from_args_env_or_wireloft(ns) -> DeviceAuthConfig:
    # 1) explicit flags win
    if ns.issuer and ns.client_id and ns.scope and ns.device_authorization_endpoint and ns.token_endpoint:
        return DeviceAuthConfig(
            issuer=ns.issuer,
            client_id=ns.client_id,
            scope=ns.scope,
            device_authorization_endpoint=ns.device_authorization_endpoint,
            token_endpoint=ns.token_endpoint,
            audience=ns.audience,
        )

    # 2) env vars (useful in scripts/CI)
    env = {
        "issuer": os.getenv("DEVICE_AUTH_ISSUER"),
        "client_id": os.getenv("DEVICE_AUTH_CLIENT_ID"),
        "scope": os.getenv("DEVICE_AUTH_SCOPE"),
        "device_authorization_endpoint": os.getenv("DEVICE_AUTH_DEVICE_ENDPOINT"),
        "token_endpoint": os.getenv("DEVICE_AUTH_TOKEN_ENDPOINT"),
        "audience": os.getenv("DEVICE_AUTH_AUDIENCE"),
    }
    if all(env[k] for k in ("issuer", "client_id", "scope", "device_authorization_endpoint", "token_endpoint")):
        return DeviceAuthConfig(
            issuer=env["issuer"], client_id=env["client_id"], scope=env["scope"],
            device_authorization_endpoint=env["device_authorization_endpoint"],
            token_endpoint=env["token_endpoint"],
            audience=env["audience"],
        )

    # 3) fall back to wireloft settings
    return DeviceAuthConfig.from_wireloft()

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="device-auth", description="OAuth 2.0 Device Authorization CLI")
    p.add_argument("--issuer")
    p.add_argument("--client-id")
    p.add_argument("--scope")
    p.add_argument("--device-authorization-endpoint")
    p.add_argument("--token-endpoint")
    p.add_argument("--audience")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Run device flow and save tokens")
    sub.add_parser("token", help="Print a valid access token (refresh if needed)")
    sub.add_parser("logout", help="Delete stored tokens")
    sub.add_parser("status", help="Show token status (expiry, presence)")
    return p

def app():
    args = _build_parser().parse_args()
    cfg = _config_from_args_env_or_wireloft(args)
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
        rec = store.load(client._make_store_key())
        if not rec:
            print("No tokens stored.")
        else:
            import time
            ttl = int(rec.expires_at - time.time())
            print(f"Token present. TTL ~ {ttl} seconds. Refresh token: {'yes' if rec.refresh_token else 'no'}")
