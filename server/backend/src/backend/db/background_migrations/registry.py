from __future__ import annotations

import pkgutil
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, Callable


class BackgroundMigrationError(RuntimeError):
    """Raised when WireLoft cannot safely resolve background migration history."""


_REVISION_RE = re.compile(r"^[0-9a-f]{12}$")


@dataclass(frozen=True)
class BackgroundMigration:
    revision: str
    down_revision: str | None
    title: str
    migrate: Callable[[Any], Any]
    module_name: str


def _validated_revision(value: object, *, field: str, module_name: str) -> str:
    if not isinstance(value, str):
        raise BackgroundMigrationError(
            f"Background migration module {module_name!r} must define a string {field}."
        )
    revision = value.strip()
    if not _REVISION_RE.fullmatch(revision):
        raise BackgroundMigrationError(
            f"Background migration {field} {revision!r} must be a 12-character "
            "lowercase hexadecimal revision, matching Alembic-style revision IDs."
        )
    return revision


def _migration_from_module(module: ModuleType) -> BackgroundMigration:
    revision = _validated_revision(
        getattr(module, "revision", None),
        field="revision",
        module_name=module.__name__,
    )
    raw_down_revision = getattr(module, "down_revision", None)
    down_revision = (
        None
        if raw_down_revision is None
        else _validated_revision(
            raw_down_revision,
            field="down_revision",
            module_name=module.__name__,
        )
    )
    migrate = getattr(module, "migrate", None)
    title = getattr(module, "title", None)

    if down_revision == revision:
        raise BackgroundMigrationError(
            f"Background migration revision {revision!r} cannot point to itself as down_revision."
        )

    leaf_name = module.__name__.rsplit(".", 1)[-1]
    expected_prefix = f"{revision}_"
    if not leaf_name.startswith(expected_prefix) or len(leaf_name) == len(expected_prefix):
        raise BackgroundMigrationError(
            f"Background migration revision {revision!r} must live in a version module "
            f"named {revision}_<description>.py; found {leaf_name}.py."
        )

    if not callable(migrate):
        raise BackgroundMigrationError(
            f"Background migration {revision!r} must define a callable migrate(context)."
        )

    if not isinstance(title, str) or not title.strip():
        doc = (module.__doc__ or "").strip().splitlines()
        title = doc[0].strip().rstrip(".") if doc else revision

    return BackgroundMigration(
        revision=revision,
        down_revision=down_revision,
        title=title.strip(),
        migrate=migrate,
        module_name=module.__name__,
    )


def _validate_migration_chain(
    migrations: list[BackgroundMigration] | tuple[BackgroundMigration, ...],
) -> tuple[BackgroundMigration, ...]:
    if not migrations:
        return ()

    by_revision: dict[str, BackgroundMigration] = {}
    for migration in migrations:
        if migration.revision in by_revision:
            raise BackgroundMigrationError(
                f"Duplicate background migration revision {migration.revision!r}."
            )
        by_revision[migration.revision] = migration

    roots = [migration for migration in migrations if migration.down_revision is None]
    if len(roots) != 1:
        raise BackgroundMigrationError(
            f"Background migration history must have exactly one root, found {len(roots)}."
        )

    successors: dict[str, list[BackgroundMigration]] = {}
    for migration in migrations:
        if migration.down_revision is None:
            continue
        if migration.down_revision not in by_revision:
            raise BackgroundMigrationError(
                f"Background migration {migration.revision!r} references unknown "
                f"down_revision {migration.down_revision!r}."
            )
        successors.setdefault(migration.down_revision, []).append(migration)

    for down_revision, children in successors.items():
        if len(children) > 1:
            child_revisions = ", ".join(sorted(child.revision for child in children))
            raise BackgroundMigrationError(
                "Background migrations must form one linear history; "
                f"{down_revision!r} has multiple successors: {child_revisions}."
            )

    ordered: list[BackgroundMigration] = []
    visited: set[str] = set()
    current = roots[0]
    while True:
        if current.revision in visited:
            raise BackgroundMigrationError(
                f"Background migration history contains a cycle at {current.revision!r}."
            )
        visited.add(current.revision)
        ordered.append(current)

        children = successors.get(current.revision, [])
        if not children:
            break
        current = children[0]

    if len(ordered) != len(migrations):
        unreachable = ", ".join(sorted(set(by_revision) - visited))
        raise BackgroundMigrationError(
            "Background migration history is disconnected or cyclic; "
            f"unreachable revisions: {unreachable}."
        )

    return tuple(ordered)


@lru_cache(maxsize=1)
def get_background_migration_history() -> tuple[BackgroundMigration, ...]:
    package = import_module("backend.db.background_migrations.versions")
    discovered: list[BackgroundMigration] = []

    for module_info in pkgutil.iter_modules(
        package.__path__,
        prefix=f"{package.__name__}.",
    ):
        leaf_name = module_info.name.rsplit(".", 1)[-1]
        if leaf_name.startswith("_"):
            continue
        discovered.append(_migration_from_module(import_module(module_info.name)))

    return _validate_migration_chain(discovered)


def get_background_migration_head_revision() -> str | None:
    history = get_background_migration_history()
    return history[-1].revision if history else None


def get_pending_background_migrations(
    current_revision: str | None,
) -> tuple[BackgroundMigration, ...]:
    history = get_background_migration_history()
    if current_revision is None:
        return history

    for index, migration in enumerate(history):
        if migration.revision == current_revision:
            return history[index + 1 :]

    raise BackgroundMigrationError(
        f"Database references unknown background migration revision {current_revision!r}."
    )
