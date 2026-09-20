from __future__ import annotations

from sqlalchemy import select, update

from backend.db.core import get_session
from backend.db.models.Settings import Settings

from .registry import (
    BackgroundMigrationError,
    get_background_migration_head_revision,
    get_pending_background_migrations,
)


def get_current_background_migration_revision() -> str | None:
    session = get_session()
    try:
        values = list(
            session.scalars(
                select(Settings.background_migration_version).order_by(Settings.id)
            )
        )
    finally:
        session.close()

    if len(values) != 1:
        raise BackgroundMigrationError(
            "WireLoft requires exactly one settings row to store the background migration revision; "
            f"found {len(values)}."
        )
    return values[0]


def advance_background_migration_revision(
    *,
    expected_revision: str | None,
    new_revision: str,
) -> None:
    """Advance the stored revision atomically after one migration succeeds."""

    session = get_session()
    try:
        statement = update(Settings)
        if expected_revision is None:
            statement = statement.where(Settings.background_migration_version.is_(None))
        else:
            statement = statement.where(
                Settings.background_migration_version == expected_revision
            )

        result = session.execute(
            statement.values(background_migration_version=new_revision)
        )
        if result.rowcount != 1:
            raise BackgroundMigrationError(
                "Background migration revision changed unexpectedly while advancing "
                f"from {expected_revision!r} to {new_revision!r}."
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def validate_background_migration_state() -> tuple[str | None, str | None]:
    current = get_current_background_migration_revision()
    head = get_background_migration_head_revision()
    get_pending_background_migrations(current)
    return current, head
