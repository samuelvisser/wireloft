from __future__ import annotations

import argparse
import json
import sys

from .config import (
    get_config,
    DEFAULT_ISSUER,
    DEFAULT_AUDIENCE,
    DEFAULT_CLIENT_ID,
    DEFAULT_SCOPE,
)
from .device_flow import generate_login_info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dailywire-auth",
        description="Generate a DailyWire Auth0 Device Authorization login URL",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON (url, user_code, device_code, interval, expires_in)",
    )
    parser.add_argument(
        "--issuer",
        default=DEFAULT_ISSUER,
        help=f"Auth0 issuer domain (default: {DEFAULT_ISSUER})",
    )
    parser.add_argument(
        "--audience",
        default=DEFAULT_AUDIENCE,
        help=f"API audience identifier (default: {DEFAULT_AUDIENCE})",
    )
    parser.add_argument(
        "--client-id",
        dest="client_id",
        default=DEFAULT_CLIENT_ID,
        help="Auth0 application client ID (default provided)",
    )
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        help=f"OAuth scope string (default: '{DEFAULT_SCOPE}')",
    )
    args = parser.parse_args(argv)

    try:
        cfg = get_config(
            issuer=args.issuer,
            audience=args.audience,
            client_id=args.client_id,
            scope=args.scope,
        )
        info = generate_login_info(cfg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        print("Login URL:", info["url"])  # may already include user_code
        if info.get("user_code"):
            print("User code:", info["user_code"])  # display in case manual entry is needed
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
