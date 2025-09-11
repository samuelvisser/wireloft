from argparse import ArgumentParser, Namespace
from typing import Dict, Any, List

from dailywire_api.cli.handlers import HANDLERS
from dailywire_api.dw_api.client import MiddlewareAPIError

# -------- Dynamic command registry --------
COMMANDS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "show": {
        "list": {
            "help": "List info for a show (prints normalized JSON)",
            "args": [
                {"name": "--slug", "dest": "slug", "required": True, "help": "Show slug (e.g. 'the-ben-shapiro-show')."},
                {"name": "--all", "dest": "all", "action": "store_true", "help": "Include all episodes."},
            ],
        }
    }
}

COMMON_ARGS = [
    {"name": "--access-token", "dest": "access_token", "default": None, "help": "Optional JWT access token (if needed for premium content)."},
    {"name": "--membership-plan", "dest": "membership_plan", "default": None, "help": "Optional membership plan to influence content selection (e.g., AllAccess)."},
    {"name": "--debug", "dest": "debug_mode", "default": None, "help": "Enable debug mode, use while developing the package."},
]

_group: str| None = None
_action: str| None = None

def _apply_args(parser: ArgumentParser, arg_specs: List[Dict[str, Any]]) -> None:
    for spec in arg_specs:
        kwargs = dict(spec)
        name = kwargs.pop("name")
        parser.add_argument(name, **kwargs)

def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
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

def configure_cli(args: Namespace) -> None:
    global _group, _action

    _group = getattr(args, "group", None) or getattr(args, "command", None)
    _action = getattr(args, "action", None) or getattr(args, f"{_group}_command", None)


def is_cli_mode(args: Namespace) -> bool:
    global _group, _action

    if not _group:
        configure_cli(args)
    return _group is not None

def perform_cli_action(parser: ArgumentParser, args: Namespace) -> int:
    global _group, _action

    configure_cli(args)

    if not _group or not _action:
        parser.print_help()
        return 0

    try:
        handler = HANDLERS[_group][_action]
    except Exception:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except MiddlewareAPIError:
        raise
    except Exception as e:
        raise MiddlewareAPIError(str(e)) from e



