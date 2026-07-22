from __future__ import annotations

import argparse
import os
import psutil
import signal
import sys
import tempfile
from pathlib import Path
from typing import Optional
import uvicorn

from backend.db import configure_db, create_tables, get_db_path, seed_db, get_engine
from sqlalchemy import text

from config.registry import get_settings
from .config import PROJECT_ROOT


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backend-api", description="WireLoft backend API and DB utilities")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    # run command
    run_parser = subparsers.add_parser("run", help="Start the backend API server")
    run_parser.add_argument("--db", dest="db", help="Path to SQLite database file")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind when running server")
    run_parser.add_argument("--port", type=int, default=5001, help="Port to bind when running server")
    run_parser.add_argument("--debug", action="store_true", help="Enable debug/reload mode")

    # db subcommand group
    db_parser = subparsers.add_parser("db", help="Database management commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True, help="Database operation")

    # db init
    db_init_parser = db_subparsers.add_parser("init", help="Initialize the database schema")
    db_init_parser.add_argument("--db", dest="db", help="Path to SQLite database file")

    # db seed
    db_seed_parser = db_subparsers.add_parser("seed", help="Seed the database with demo data")
    db_seed_parser.add_argument("--db", dest="db", help="Path to SQLite database file")

    # stop command
    subparsers.add_parser("stop", help="Stop all running backend-api processes")

    return parser.parse_args(argv)

def _get_db_path(args) -> Path:
    if hasattr(args, 'db') and args.db:
        return Path(args.db)
    return get_settings().database_path

def _validate_db_health() -> None:
    # 1) Ensure the SQLite file exists to avoid silent auto-creation
    if not get_db_path().exists():
        print(
            f"Database file not found: {get_db_path()}\nRun 'backend-api db init' to initialize the schema, or provide --db to set the path.",
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
            print("Database is empty (no tables). Run 'backend-api db init' to initialize the schema.", file=sys.stderr)
            sys.exit(1)
    except Exception:
        # If inspection fails, let the app start; runtime errors will surface
        pass

def _reload_startup_marker(supervisor_pid: str) -> Path:
    """Marker file shared by all worker subprocesses of one reload session."""
    return Path(tempfile.gettempdir()) / f"wireloft-reload-startup-{supervisor_pid}.lock"


def _stop_backend() -> None:
    """Stop all running backend-api processes"""
    stopped_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and any('backend-api' in str(arg) for arg in cmdline):
                print(f"Stopping backend-api process (PID: {proc.info['pid']})")
                proc.send_signal(signal.SIGTERM)
                stopped_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    if stopped_count == 0:
        print("No running backend-api processes found")
    else:
        print(f"Stopped {stopped_count} backend-api process(es)")

def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)

    # Handle stop command
    if args.command == "stop":
        _stop_backend()
        return

    # Handle db commands
    if args.command == "db":
        os.environ["WIRELOFT_DB_PATH"] = str(_get_db_path(args))
        configure_db()

        if args.db_command == "init":
            create_tables()
            print(f"Initialized database at: {os.environ.get('WIRELOFT_DB_PATH')}")
            return

        if args.db_command == "seed":
            seed_db()
            print(f"Seeded database at: {os.environ.get('WIRELOFT_DB_PATH')}")
            return

    # Handle run command
    if args.command == "run":
        os.environ["WIRELOFT_DB_PATH"] = str(_get_db_path(args))

        print("Starting Wireloft backend...")
        configure_db()

        # Validate database health before starting server
        _validate_db_health()
        debug = args.debug

        if debug:
            # In reload mode this process becomes uvicorn's long-lived reloader
            # supervisor; worker subprocesses inherit its environment. Stamp a
            # session token so workers can tell the first startup from a reload,
            # and clear any stale marker left by a crashed prior run of this pid.
            supervisor_pid = str(os.getpid())
            os.environ["WIRELOFT_RELOAD_SUPERVISOR_PID"] = supervisor_pid
            _reload_startup_marker(supervisor_pid).unlink(missing_ok=True)

        try:
            uvicorn.run(
                "backend.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                reload=debug,
                reload_dirs=str(PROJECT_ROOT / "server"),
                log_level="debug" if debug else "info"
            )
        finally:
            if debug:
                _reload_startup_marker(os.getpid()).unlink(missing_ok=True)

if __name__ == "__main__":
    main(sys.argv[1:])
