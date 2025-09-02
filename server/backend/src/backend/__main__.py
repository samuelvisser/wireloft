from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from backend.db import configure, create_all, get_db_path
from .app import create_app
from .dblegacy import seed_db, connect_db
from .config import DEFAULT_DB_PATH

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend-api", description="WireLoft backend API and DB utilities")
    parser.add_argument("--db", dest="db", help=f"Path to SQLite database file")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database schema using SQLAlchemy ORM and exit")
    parser.add_argument("--seed-db", action="store_true", help="Seed the database with demo data and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Flask host (when running server)")
    parser.add_argument("--port", type=int, default=5000, help="Flask port (when running server)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args(argv)

def _get_db_path(args) -> Path:
    if args.db:
        return Path(args.db)
    return Path(os.environ.get("WIRELOFT_DB_PATH", DEFAULT_DB_PATH))

def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    db_path = _get_db_path(args)
    configure(db_path)

    # Manual CLI utilities: only run when flags are provided
    if args.init_db:
        create_all()
        print(f"Initialized database at: {db_path}")
        return

    if args.seed_db:
        seed_db(db_path.as_posix())
        print(f"Seeded database at: {db_path}")
        return

    # Otherwise, start the Flask API server
    # Ensure DB exists before creating the app (fail fast with a clear message)
    try:
        conn = connect_db(db_path.as_posix())
        conn.close()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    app = create_app()
    debug = args.debug
    app.run(host=args.host, port=args.port, debug=debug)

if __name__ == "__main__":
    main(sys.argv[1:])
