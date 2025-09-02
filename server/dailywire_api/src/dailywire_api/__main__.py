"""
Command-line entry point for the dailywire_api package.

Usage examples (PowerShell):
  dailywire-api show list --slug the-ben-shapiro-show
"""

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, List

from dailywire_api.middleware.client import MiddlewareAPIError, MiddlewareClient


# -------- Dynamic command registry --------
CommandHandler = Callable[[argparse.Namespace], int]

COMMANDS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "show": {
        "list": {
            "help": "List info for a show (prints normalized JSON)",
            "args": [
                {"name": "--slug", "dest": "slug", "required": True, "help": "Show slug (e.g. 'the-ben-shapiro-show')."},
            ],
        }
    }
}

COMMON_ARGS = [
    {"name": "--access-token", "dest": "access_token", "default": None, "help": "Optional JWT access token (if needed for premium content)."},
    {"name": "--membership-plan", "dest": "membership_plan", "default": None, "help": "Optional membership plan to influence content selection (e.g., AllAccess)."},
    {"name": "--json", "action": "store_true", "help": "Output JSON instead of plain lines."},
    {"name": "--all", "dest": "all", "action": "store_true", "help": "Include all episodes."},
]


def _apply_args(parser: argparse.ArgumentParser, arg_specs: List[Dict[str, Any]]) -> None:
    for spec in arg_specs:
        kwargs = dict(spec)
        name = kwargs.pop("name")
        parser.add_argument(name, **kwargs)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailywire-api",
        description="DailyWire API CLI",
    )

    # Top-level common args
    _apply_args(parser, COMMON_ARGS)

    # Dynamic subcommands from registry
    subparsers = parser.add_subparsers(dest="command")
    for group, actions in COMMANDS.items():
        group_parser = subparsers.add_parser(group, help=f"{group.capitalize()}-related commands")
        group_parser.set_defaults(group=group)
        group_sub = group_parser.add_subparsers(dest=f"{group}_command")
        for action, meta in actions.items():
            action_parser = group_sub.add_parser(action, help=meta.get("help"))
            _apply_args(action_parser, meta.get("args", []))
            # Allow common options after subcommand as well
            _apply_args(action_parser, COMMON_ARGS)
            action_parser.set_defaults(action=action)

    return parser


# -------- Handlers --------

def handle_show_list(args: argparse.Namespace) -> int:
    token = args.access_token or os.getenv("DAILYWIRE_ACCESS_TOKEN")
    client = MiddlewareClient(access_token=token)
    payload = client.get_show_page(slug=args.slug, membership_plan=args.membership_plan)

    # Output
    print(json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": ")))
    return 0


HANDLERS: Dict[str, Dict[str, CommandHandler]] = {
    "show": {
        "list": handle_show_list,
    }
}


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    group = getattr(args, "group", None) or getattr(args, "command", None)
    action = getattr(args, "action", None) or getattr(args, f"{group}_command", None)

    if not group or not action:
        parser.print_help()
        return 0

    try:
        handler = HANDLERS[group][action]
    except Exception:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except MiddlewareAPIError:
        raise
    except Exception as e:
        raise MiddlewareAPIError(str(e)) from e


if __name__ == "__main__":
    raise SystemExit(main())
