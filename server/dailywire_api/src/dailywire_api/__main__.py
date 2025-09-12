"""
Command-line entry point for the dailywire_api package.

Usage examples (PowerShell):
  dailywire-api show list --slug the-ben-shapiro-show
"""

import sys
from typing import List

from dailywire_api.cli import build_parser, perform_cli_action


def main(argv: List[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    status = perform_cli_action(parser, args)
    raise SystemExit(status)

if __name__ == "__main__":
    main(sys.argv[1:])
