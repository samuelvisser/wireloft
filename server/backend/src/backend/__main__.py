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
from sqlalchemy import text

from backend.db import configure_db, get_db_path, get_engine, seed_db
from backend.db.migrations import (
    DatabaseMigrationError,
    check_database,
    create_revision,
    get_database_status,
    initialize_database,
    require_database_current,
    show_history,
    upgrade_database,
)
from config.registry import get_settings
from .config import PROJECT_ROOT


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="backend-api",
        description="WireLoft backend API and DB utilities",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    run_parser = subparsers.add_parser("run", help="Start the backend API server")
    run_parser.add_argument("--db", dest="db", help="Path to SQLite database file")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind when running server")
    run_parser.add_argument("--port", type=int, default=5001, help="Port to bind when running server")
    run_parser.add_argument("--debug", action="store_true", help="Enable debug/reload mode")

    db_parser = subparsers.add_parser("db", help="Database management commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True, help="Database operation")

    for command_name, help_text in (
        ("init", "Initialize a new or empty database at the latest schema"),
        ("upgrade", "Apply all pending database migrations"),
        ("current", "Show the current and latest database revisions"),
        ("history", "Show the Alembic migration history"),
        ("check", "Verify the DB is current and ORM metadata matches migrations"),
        ("seed", "Seed the database with demo data"),
    ):
        command_parser = db_subparsers.add_parser(command_name, help=help_text)
        command_parser.add_argument("--db", dest="db", help="Path to SQLite database file")

    revision_parser = db_subparsers.add_parser(
        "revision",
        help="Generate an Alembic revision from ORM model changes",
    )
    revision_parser.add_argument("--db", dest="db", help="Path to SQLite database file")
    revision_parser.add_argument("-m", "--message", required=True, help="Migration description")

    subparsers.add_parser("stop", help="Stop all running backend-api processes")
    return parser.parse_args(argv)


def _get_db_path(args: argparse.Namespace) -> Path:
    if hasattr(args, "db") and args.db:
        return Path(args.db)
    return get_settings().database_path


def _validate_db_health() -> None:
    if not get_db_path().exists():
        print(
            f"Database file not found: {get_db_path()}\n"
            "Run 'backend-api db init' to initialize the schema, or provide --db to set the path.",
            file=sys.stderr,
        )
        sys.exit(1)

    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"Failed to connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        if not inspector.get_table_names():
            print(
                "Database is empty (no tables). Run 'backend-api db init' to initialize the schema.",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception:
        pass


def _reload_startup_marker(supervisor_pid: str) -> Path:
    """Marker file shared by all worker subprocesses of one reload session."""
    return Path(tempfile.gettempdir()) / f"wireloft-reload-startup-{supervisor_pid}.lock"


_STOP_SIGTERM_TIMEOUT_S = 5.0


def _matches_backend_api(cmdline: Optional[list[str]]) -> bool:
    """Whether a process's cmdline looks like a backend-api invocation."""
    if not cmdline:
        return False
    return any(
        arg == "backend-api" or arg.endswith(("/backend-api", "\\backend-api"))
        for arg in cmdline
    )


def _stop_backend() -> None:
    """Stop all other running backend-api processes."""
    own_pid = os.getpid()
    targets: dict[int, psutil.Process] = {}

    for proc in psutil.process_iter(["pid", "cmdline"]):
        if proc.pid == own_pid:
            continue
        try:
            if _matches_backend_api(proc.info.get("cmdline")):
                targets[proc.pid] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not targets:
        print("No running backend-api processes found")
        return

    for proc in list(targets.values()):
        try:
            for child in proc.children(recursive=True):
                targets.setdefault(child.pid, child)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    for proc in targets.values():
        try:
            print(f"Stopping backend-api process (PID: {proc.pid})")
            proc.send_signal(signal.SIGTERM)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    _gone, alive = psutil.wait_procs(
        list(targets.values()),
        timeout=_STOP_SIGTERM_TIMEOUT_S,
    )
    for proc in alive:
        try:
            print(f"Process {proc.pid} did not stop in time; killing it")
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=_STOP_SIGTERM_TIMEOUT_S)

    print(f"Stopped {len(targets)} backend-api process(es)")


def _configure_database_for_args(args: argparse.Namespace) -> None:
    os.environ["WL_DATABASE_PATH"] = str(_get_db_path(args))
    configure_db()


def _handle_db_command(args: argparse.Namespace) -> None:
    _configure_database_for_args(args)

    if args.db_command == "init":
        initialize_database()
        print(f"Initialized database at: {get_db_path()}")
        return

    if args.db_command == "upgrade":
        upgrade_database()
        _current, head = get_database_status()
        print(f"Database upgraded to: {head} ({get_db_path()})")
        return

    if args.db_command == "current":
        current, head = get_database_status()
        current_label = ", ".join(current) if current else "base / not initialized"
        status = "up to date" if current == (head,) else "upgrade required"
        print(f"Current database revision: {current_label}")
        print(f"Latest WireLoft revision:  {head}")
        print(f"Status: {status}")
        return

    if args.db_command == "history":
        show_history()
        return

    if args.db_command == "check":
        check_database()
        print("Database revision and ORM metadata are in sync.")
        return

    if args.db_command == "revision":
        create_revision(args.message)
        return

    if args.db_command == "seed":
        require_database_current()
        seed_db()
        print(f"Seeded database at: {get_db_path()}")
        return

    raise RuntimeError(f"Unsupported database command: {args.db_command}")


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)

    if args.command == "stop":
        _stop_backend()
        return

    try:
        if args.command == "db":
            _handle_db_command(args)
            return

        if args.command == "run":
            _configure_database_for_args(args)

            print("Starting Wireloft backend...")
            _validate_db_health()
            require_database_current()
            debug = args.debug

            if debug:
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
                    log_level="debug" if debug else "info",
                )
            finally:
                if debug:
                    _reload_startup_marker(os.getpid()).unlink(missing_ok=True)
            return
    except DatabaseMigrationError as exc:
        print(f"Database migration error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
