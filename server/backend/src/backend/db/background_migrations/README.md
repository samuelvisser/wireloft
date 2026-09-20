# Background migrations

Background migrations repair historical application data without blocking WireLoft startup.
They are intentionally separate from Alembic:

- Alembic makes the database schema compatible before the backend starts.
- Background migrations bring already-stored data up to the semantics expected by current code.

## Revisions and version files

Background migration identity follows the same model as Alembic. Revisions are opaque,
12-character lowercase hexadecimal IDs; descriptions belong in the filename suffix and title,
never in the revision itself.

Create version modules in `versions/` using this filename form:

```text
a1b2c3d4e5f6_refresh_historical_episode_identifiers.py
```

The module declares its own revision and previous revision:

```python
revision = "a1b2c3d4e5f6"
down_revision = None
title = "Refresh historical episode identifiers"


async def migrate(context) -> None:
    ...
```

A later migration sets `down_revision` to the previous migration's `revision`. The registry
verifies that the filename begins with its declared revision and rejects descriptive/non-Alembic-style
revision IDs, duplicate revisions, missing down revisions, branches, cycles and disconnected histories.

When prerelease background migrations are consolidated for a WireLoft release, the consolidated
migration must keep the revision of the latest migration it replaces. Databases that already reached
that revision then remain current without rerunning the consolidated work.

The authoritative applied position is `settings.background_migration_version`. Despite the column's
historical name, its value is the opaque revision ID, not a description. The runner reads that value
every time it starts and returns immediately when it is already at the current head. After a migration
finishes successfully, the runner atomically advances Settings from the migration's
`down_revision` to its `revision`.

Migration implementations must therefore be idempotent: a process can stop after data was changed
but before the revision was advanced, causing that migration to run again. Prefer querying for rows
that still need repair rather than repeating all historical work.

Do not hold a database transaction or checked-out connection across slow network calls. Use
short-lived sessions around reads/writes, and report granular work with
`context.update_progress(current, total, message)` for long migrations. Use
`context.raise_if_cancelled()` at useful checkpoints.

TaskOperation is only the execution layer. It provides progress, retries, restart recovery and UI
visibility for the single `background_migration_runner` task; it is never the migration ledger.

The runner is registered as critical work with `pauses_scheduled_work=True`. It executes on the
scheduler's dedicated critical lane while the normal scheduler remains paused. That pause survives
TaskRun retries and is released only when the migration TaskRun becomes terminal. Startup filesystem
recovery uses the same reference-counted pause mechanism, so overlapping maintenance cannot resume
normal work prematurely.

## CLI

Use either command name:

```text
backend-api background-migrations current
backend-api migrate current
backend-api migrate history
backend-api migrate check
```

There is deliberately no background-migration `upgrade` CLI command. Pending migrations are run by
the normal background runner after WireLoft starts.
