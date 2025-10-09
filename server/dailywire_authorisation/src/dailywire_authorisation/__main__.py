from __future__ import annotations

from dailywire_authorisation import cli

def main() -> int:
    cli.run_cli()
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
