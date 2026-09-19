from __future__ import annotations

import pkgutil
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, Callable


class BackgroundMigrationError(RuntimeError):
    """Raised when WireLoft cannot safely resolve background migration history."""


@dataclass(frozen=True)
class BackgroundMigration:
    key: str
    upstream_key: str | None
    title: str
    migrate: Callable[[Any], Any]
    module_name: str


def _migration_from_module(module: ModuleType) -> BackgroundMigration:
    key = getattr(module, "key", None)
    upstream_key = getattr(module, "upstream_key", None)
    migrate = getattr(module, "migrate", None)
    title = getattr(module, "title", None)

    if not isinstance(key, str) or not key.strip():
        raise BackgroundMigrationError(
            f"Background migration module {module.__name__!r} must define a non-empty string key."
        )
    key = key.strip()
    if len(key) > 32:
        raise BackgroundMigrationError(
            f"Background migration key {key!r} exceeds the 32-character Settings storage limit."
        )
    if upstream_key is not None and not isinstance(upstream_key, str):
        raise BackgroundMigrationError(
            f"Background migration {key!r} has a non-string upstream_key."
        )
    if upstream_key is not None:
        upstream_key = upstream_key.strip()
        if not upstream_key:
            raise BackgroundMigrationError(
                f"Background migration {key!r} has an empty upstream_key."
            )
    if upstream_key == key:
        raise BackgroundMigrationError(
            f"Background migration {key!r} cannot point to itself as upstream."
        )
    if not callable(migrate):
        raise BackgroundMigrationError(
            f"Background migration {key!r} must define a callable migrate(context)."
        )

    if not isinstance(title, str) or not title.strip():
        doc = (module.__doc__ or "").strip().splitlines()
        title = doc[0].strip().rstrip(".") if doc else key

    return BackgroundMigration(
        key=key,
        upstream_key=upstream_key,
        title=title.strip(),
        migrate=migrate,
        module_name=module.__name__,
    )


def _validate_migration_chain(
    migrations: list[BackgroundMigration] | tuple[BackgroundMigration, ...],
) -> tuple[BackgroundMigration, ...]:
    if not migrations:
        return ()

    by_key: dict[str, BackgroundMigration] = {}
    for migration in migrations:
        if migration.key in by_key:
            raise BackgroundMigrationError(
                f"Duplicate background migration key {migration.key!r}."
            )
        by_key[migration.key] = migration

    roots = [migration for migration in migrations if migration.upstream_key is None]
    if len(roots) != 1:
        raise BackgroundMigrationError(
            f"Background migration history must have exactly one root, found {len(roots)}."
        )

    successors: dict[str, list[BackgroundMigration]] = {}
    for migration in migrations:
        if migration.upstream_key is None:
            continue
        if migration.upstream_key not in by_key:
            raise BackgroundMigrationError(
                f"Background migration {migration.key!r} references unknown upstream "
                f"key {migration.upstream_key!r}."
            )
        successors.setdefault(migration.upstream_key, []).append(migration)

    for upstream_key, children in successors.items():
        if len(children) > 1:
            child_keys = ", ".join(sorted(child.key for child in children))
            raise BackgroundMigrationError(
                "Background migrations must form one linear history; "
                f"{upstream_key!r} has multiple successors: {child_keys}."
            )

    ordered: list[BackgroundMigration] = []
    visited: set[str] = set()
    current = roots[0]
    while True:
        if current.key in visited:
            raise BackgroundMigrationError(
                f"Background migration history contains a cycle at {current.key!r}."
            )
        visited.add(current.key)
        ordered.append(current)

        children = successors.get(current.key, [])
        if not children:
            break
        current = children[0]

    if len(ordered) != len(migrations):
        unreachable = ", ".join(sorted(set(by_key) - visited))
        raise BackgroundMigrationError(
            "Background migration history is disconnected or cyclic; "
            f"unreachable keys: {unreachable}."
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


def get_background_migration_head_key() -> str | None:
    history = get_background_migration_history()
    return history[-1].key if history else None


def get_pending_background_migrations(
    current_key: str | None,
) -> tuple[BackgroundMigration, ...]:
    history = get_background_migration_history()
    if current_key is None:
        return history

    for index, migration in enumerate(history):
        if migration.key == current_key:
            return history[index + 1 :]

    raise BackgroundMigrationError(
        f"Database references unknown background migration key {current_key!r}."
    )
