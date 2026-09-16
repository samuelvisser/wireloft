"""Repair legacy SQLite scheduler and foreign-key orphans.

Revision ID: a4e7d18c2f90
Revises: f2c6a9d41e7b
"""

from alembic import op
import sqlalchemy as sa


revision = "a4e7d18c2f90"
down_revision = "f2c6a9d41e7b"
branch_labels = None
depends_on = None


# HasTaskResourcesMixin owns these polymorphic resource keys. They cannot use a
# normal database foreign key because one resource_id column points at multiple
# domain tables, so legacy cleanup must mirror that ownership explicitly.
_TASK_RESOURCE_TABLES = {
    "show": "shows",
    "season": "seasons",
    "episode": "media_items_episode",
    "movie": "media_items_movie",
    "movie_extra": "media_items_movie_extra",
    "media_download": "media_downloads",
    "download_profile": "download_profiles",
    "download_profile_series": "download_profiles",
}


def _delete_broken_scheduler_foreign_keys(connection) -> None:
    # Historical SQLite connections did not enable foreign-key enforcement, so
    # rows that should have been removed by ON DELETE CASCADE can survive their
    # parent operation/run/target. Remove the deepest link rows first.
    connection.execute(sa.text("""
        DELETE FROM task_operation_runs
        WHERE NOT EXISTS (
            SELECT 1
            FROM task_operation_targets
            WHERE task_operation_targets.id = task_operation_runs.target_id
        )
        OR NOT EXISTS (
            SELECT 1
            FROM task_runs
            WHERE task_runs.id = task_operation_runs.task_run_id
        )
        OR NOT EXISTS (
            SELECT 1
            FROM task_operations
            WHERE task_operations.id = task_operation_runs.operation_id
        )
    """))
    connection.execute(sa.text("""
        DELETE FROM task_operation_targets
        WHERE NOT EXISTS (
            SELECT 1
            FROM task_operations
            WHERE task_operations.id = task_operation_targets.operation_id
        )
    """))


def _missing_resource_query(*, scheduler_table: str, resource_key: str, resource_table: str) -> str:
    return f"""
        SELECT id
        FROM {scheduler_table}
        WHERE lower(resource_type) = '{resource_key}'
          AND resource_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {resource_table}
              WHERE {resource_table}.id = {scheduler_table}.resource_id
          )
    """


def _delete_orphaned_polymorphic_resources(connection) -> None:
    # HasTaskResourcesMixin says scheduler history belongs to the resource and is
    # deleted with it. Clean rows left by pre-enforcement/legacy delete paths so
    # recycled integer ids cannot inherit another resource's old task history.
    for resource_key, resource_table in _TASK_RESOURCE_TABLES.items():
        stale_targets = _missing_resource_query(
            scheduler_table="task_operation_targets",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE target_id IN ({stale_targets})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_targets
            WHERE id IN ({stale_targets})
        """))

        stale_runs = _missing_resource_query(
            scheduler_table="task_runs",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE task_run_id IN ({stale_runs})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_runs
            WHERE id IN ({stale_runs})
        """))

        stale_operations = _missing_resource_query(
            scheduler_table="task_operations",
            resource_key=resource_key,
            resource_table=resource_table,
        )
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_runs
            WHERE operation_id IN ({stale_operations})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operation_targets
            WHERE operation_id IN ({stale_operations})
        """))
        connection.execute(sa.text(f"""
            DELETE FROM task_operations
            WHERE id IN ({stale_operations})
        """))

        connection.execute(sa.text(f"""
            DELETE FROM task_schedules
            WHERE lower(resource_type) = '{resource_key}'
              AND resource_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM {resource_table}
                  WHERE {resource_table}.id = task_schedules.resource_id
              )
        """))


def _delete_orphaned_media_download_subtypes(connection) -> None:
    for table_name in (
        "media_downloads_episode",
        "media_downloads_movie",
        "media_downloads_movie_extra",
    ):
        connection.execute(sa.text(f"""
            DELETE FROM {table_name}
            WHERE NOT EXISTS (
                SELECT 1
                FROM media_downloads
                WHERE media_downloads.id = {table_name}.id
            )
        """))


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return

    _delete_broken_scheduler_foreign_keys(connection)
    _delete_orphaned_polymorphic_resources(connection)
    _delete_orphaned_media_download_subtypes(connection)


def downgrade() -> None:
    # Deleted rows had no owning parent and cannot be reconstructed safely.
    pass
