"""
Command-line entry point for the dailywire_api package.

Usage examples (PowerShell):
  python -m dailywire_api --show what-we-saw
  python -m dailywire_api --show what-we-saw --json
  python -m dailywire_api --show what-we-saw --access-token <JWT>
"""

import argparse
import json
import os
import sys
from typing import Any, List

from .app import DailyWireAPI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywire-api",
        description="List episodes for a DailyWire show using the Middleware API.",
    )
    parser.add_argument(
        "--show",
        dest="show_slug",
        help="Show slug (e.g. 'the-ben-shapiro-show'). If omitted, only help is shown.",
    )
    parser.add_argument(
        "--access-token",
        dest="access_token",
        default=None,
        help="Optional JWT access token (if needed for premium content).",
    )
    parser.add_argument(
        "--membership-plan",
        dest="membership_plan",
        default=None,
        help="Optional membership plan to influence content selection (e.g., AllAccess).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of plain lines.",
    )
    parser.add_argument(
        "--all",
        dest="all",
        action="store_true",
        help="Include all episodes (enumerate across seasons and pages) instead of just the latest.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.show_slug:
        parser.print_help()
        return 0

    token = args.access_token or os.getenv("DAILYWIRE_ACCESS_TOKEN")
    api = DailyWireAPI(access_token=token, membership_plan=args.membership_plan)

    try:
        episodes = api.list_show_episodes(args.show_slug, all_episodes=getattr(args, 'all', False))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        # serialize dataclasses as dicts
        payload: Any = [
            {"slug": e.slug, "url": e.url, "season_slug": e.season_slug}
            for e in episodes
        ]
        print(json.dumps(payload, indent=2))
        return 0

    for e in episodes:
        print(e.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
