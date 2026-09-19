# Background migrations

Background migrations repair historical application data without blocking WireLoft startup.
They are intentionally separate from Alembic:

- Alembic makes the database schema compatible before the backend starts.
- Background migrations bring already-stored data up to the semantics expected by current code.

## Adding a migration

Create a module in `versions/`:

```python
key = "a1b2c3d4e5f6"
upstream_key = None
title = "Refresh historical episode identifiers"


async def migrate(context) -> None:
    ...
```

Every later migration points to the previous key. The registry rejects duplicate keys, missing
upstreams, branches, cycles and disconnected histories, so the versions always form one ordered
chain. Background migrations have no downgrade function.

The authoritative applied position is `settings.background_migration_version`. The runner reads
that value every time it starts and returns immediately when it is already at the current head.
After a migration finishes successfully, the runner atomically advances the Settings key from the
migration's `upstream_key` to its `key`.

Migration implementations must therefore be idempotent: a process can stop after data was changed
but before the version key was advanced, causing that migration to run again. Prefer querying for
rows that still need repair rather than repeating all historical work.

Do not hold a database transaction or checked-out connection across slow network calls. Use
short-lived sessions around reads/writes, and report granular work with
`context.update_progress(current, total, message)` for long migrations. Use
`context.raise_if_cancelled()` at useful checkpoints.

TaskOperation is only the execution layer. It provides progress, retries, restart recovery and UI
visibility for the single `background_migration_runner` task; it is never the migration ledger.

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
