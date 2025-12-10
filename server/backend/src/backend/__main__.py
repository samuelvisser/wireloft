from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional
import uvicorn

from backend.db import configure_db, create_tables, get_db_path, seed_db, get_engine
from sqlalchemy import text

from wireloft_config.registry import get_settings
from .config import PROJECT_ROOT


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend-api", description="WireLoft backend API and DB utilities")
    parser.add_argument("--db", dest="db", help=f"Path to SQLite database file")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database schema using SQLAlchemy ORM and exit")
    parser.add_argument("--seed-db", action="store_true", help="Seed the database with demo data and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind when running server")
    parser.add_argument("--port", type=int, default=5001, help="Port to bind when running server")
    parser.add_argument("--debug", action="store_true", help="Enable debug/reload mode")
    return parser.parse_args(argv)

def _get_db_path(args) -> Path:
    if args.db:
        return Path(args.db)
    return get_settings().database_path

def _validate_db_health() -> None:
    # 1) Ensure the SQLite file exists to avoid silent auto-creation
    if not get_db_path().exists():
        print(
            f"Database file not found: {get_db_path()}\nRun with --init-db to initialize the schema, or provide --db to set the path.",
            file=sys.stderr)
        sys.exit(1)

    # 2) Validate connectivity via SQLAlchemy (fail fast)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"Failed to connect to database: {e}", file=sys.stderr)
        sys.exit(1)

    # 3) Optionally, check that tables exist; guide user if schema missing
    try:
        from sqlalchemy import inspect as _sa_inspect
        inspector = _sa_inspect(engine)
        if not inspector.get_table_names():
            print("Database is empty (no tables). Run with --init-db to initialize the schema.", file=sys.stderr)
            sys.exit(1)
    except Exception:
        # If inspection fails, let the app start; runtime errors will surface
        pass

def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    os.environ["WIRELOFT_DB_PATH"] = str(_get_db_path(args))

    print("Starting Wireloft backend...")
    configure_db()

    # Manual CLI utilities: only run when flags are provided
    if args.init_db:
        create_tables()
        print(f"Initialized database at: {os.environ.get("WIRELOFT_DB_PATH")}")
        return

    if args.seed_db:
        seed_db()
        print(f"Seeded database at: {os.environ.get("WIRELOFT_DB_PATH")}")
        return

    # Otherwise, start the FastAPI server via Uvicorn
    _validate_db_health()
    debug = args.debug
    uvicorn.run(
        "backend.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=debug,
        reload_dirs=str(PROJECT_ROOT / "server"),
        log_level="debug" if debug else "info"
    )

if __name__ == "__main__":
    main(sys.argv[1:])
