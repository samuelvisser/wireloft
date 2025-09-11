"""
Command-line entry point for the dailywire_api package.

Usage examples (PowerShell):
  dailywire-api show list --slug the-ben-shapiro-show
"""

import sys
from typing import List

import uvicorn

from dailywire_api.config import PACKAGE_ROOT
from dailywire_api.cli import is_cli_mode, build_parser, perform_cli_action


def main(argv: List[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if is_cli_mode(args):
        status = perform_cli_action(parser, args)
        raise SystemExit(status)

    debug = args.debug_mode
    uvicorn.run(
        "backend.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=debug,
        reload_dirs=[PACKAGE_ROOT.as_posix()],
        log_level="debug" if debug else "info"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
