from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from .registry import (
    BackgroundMigration,
    get_background_migration_head_revision,
    get_pending_background_migrations,
)
from .state import (
    advance_background_migration_revision,
    get_current_background_migration_revision,
)


@dataclass(frozen=True)
class BackgroundMigrationRunResult:
    current_revision: str | None
    applied_revisions: tuple[str, ...]


class BackgroundMigrationContext:
    """Progress and cancellation channel exposed to one background migration."""

    def __init__(
        self,
        *,
        migration: BackgroundMigration,
        migration_index: int,
        migration_total: int,
        progress: Any = None,
    ) -> None:
        self.migration = migration
        self.migration_index = migration_index
        self.migration_total = migration_total
        self._progress = progress

    def raise_if_cancelled(self) -> None:
        if self._progress is not None and hasattr(self._progress, "raise_if_cancelled"):
            self._progress.raise_if_cancelled()

    def _set(
        self,
        *,
        fraction: float,
        message: str,
        item_current: int | None = None,
        item_total: int | None = None,
    ) -> None:
        if self._progress is None:
            return

        overall = (
            (self.migration_index - 1) + max(0.0, min(1.0, fraction))
        ) / self.migration_total
        meta = {
            "migration_revision": self.migration.revision,
            "migration_title": self.migration.title,
            "migration_current": self.migration_index,
            "migration_total": self.migration_total,
        }
        if item_current is not None:
            meta["item_current"] = item_current
        if item_total is not None:
            meta["item_total"] = item_total

        self._progress.set(
            int(overall * 100),
            message,
            meta=meta,
        )

    def started(self) -> None:
        self._set(fraction=0, message=self.migration.title)

    def completed(self) -> None:
        self._set(fraction=1, message=f"Completed {self.migration.title}")

    def update_progress(
        self,
        current: int,
        total: int,
        message: str | None = None,
    ) -> None:
        if total <= 0:
            raise ValueError("Background migration progress total must be positive")
        current = max(0, min(int(current), int(total)))
        self._set(
            fraction=current / total,
            message=message or self.migration.title,
            item_current=current,
            item_total=total,
        )


async def run_pending_background_migrations(
    *,
    progress: Any = None,
) -> BackgroundMigrationRunResult:
    """Run every unapplied migration in strict registry order.

    The Settings revision is the source of truth. TaskOperation state is deliberately
    not consulted here, so retries and restart recovery can invoke the runner
    again without repeating migrations that already completed.
    """

    head = get_background_migration_head_revision()
    if head is None:
        return BackgroundMigrationRunResult(current_revision=None, applied_revisions=())

    current = get_current_background_migration_revision()
    if current == head:
        return BackgroundMigrationRunResult(current_revision=current, applied_revisions=())

    pending = get_pending_background_migrations(current)
    applied: list[str] = []

    for index, migration in enumerate(pending, start=1):
        context = BackgroundMigrationContext(
            migration=migration,
            migration_index=index,
            migration_total=len(pending),
            progress=progress,
        )
        context.raise_if_cancelled()
        context.started()

        result = migration.migrate(context)
        if inspect.isawaitable(result):
            await result

        context.raise_if_cancelled()
        advance_background_migration_revision(
            expected_revision=migration.down_revision,
            new_revision=migration.revision,
        )
        applied.append(migration.revision)
        current = migration.revision
        context.completed()

    return BackgroundMigrationRunResult(
        current_revision=current,
        applied_revisions=tuple(applied),
    )
