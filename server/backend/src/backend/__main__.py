from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from .app import create_app
from .dblegacy import init_db, seed_db, DEFAULT_DB_PATH, connect_db

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend-api", description="WireLoft backend API and DB utilities")
    parser.add_argument("--db", dest="db", help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--init-db", action="store_true", help="Create the SQLite database/tables and exit")
    parser.add_argument("--seed-db", action="store_true", help="Seed the database with demo data and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Flask host (when running server)")
    parser.add_argument("--port", type=int, default=5000, help="Flask port (when running server)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args(argv)

def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)

    # If a custom DB path is provided, propagate it so create_app/DB helpers use it
    if args.db:
        os.environ["WIRELOFT_DB_PATH"] = os.path.abspath(args.db)

    # Manual CLI utilities: only run when flags are provided
    if args.init_db:
        init_db(args.db)
        print(f"Initialized database at: {args.db or DEFAULT_DB_PATH}")
        return

    if args.seed_db:
        seed_db(args.db)
        print(f"Seeded database at: {args.db or DEFAULT_DB_PATH}")
        return

    # Otherwise, start the Flask API server
    # Ensure DB exists before creating the app (fail fast with a clear message)
    try:
        conn = connect_db(args.db)
        conn.close()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    app = create_app()
    debug = args.debug
    app.run(host=args.host, port=args.port, debug=debug)

if __name__ == "__main__":
    main(sys.argv[1:])
