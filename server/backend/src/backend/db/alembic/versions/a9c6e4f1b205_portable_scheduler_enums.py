"""Make scheduler enum columns portable across SQLAlchemy backends.

Revision ID: a9c6e4f1b205
Revises: e3a1b5c7d902
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c6e4f1b205"
down_revision = "e3a1b5c7d902"
branch_labels = None
depends_on = None

_RESOURCE_TYPE_LENGTH = 23
_TASK_STATUS_LENGTH = 15


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # SQLite already persisted SQLAlchemy Enum values as VARCHAR, so changing
    # the ORM to native_enum=False does not require an on-disk schema rewrite.
    if dialect == "sqlite":
        return

    if dialect == "postgresql":
        op.alter_column(
            "task_schedules",
            "resource_type",
            type_=sa.String(length=_RESOURCE_TYPE_LENGTH),
            postgresql_using="resource_type::text",
        )
        op.alter_column(
            "task_runs",
            "resource_type",
            type_=sa.String(length=_RESOURCE_TYPE_LENGTH),
            postgresql_using="resource_type::text",
        )
        op.alter_column(
            "task_runs",
            "status",
            type_=sa.String(length=_TASK_STATUS_LENGTH),
            postgresql_using="status::text",
        )
        op.execute(sa.text("DROP TYPE IF EXISTS resourcetype"))
        op.execute(sa.text("DROP TYPE IF EXISTS taskstatus"))
        return

    with op.batch_alter_table("task_schedules") as batch:
        batch.alter_column(
            "resource_type",
            type_=sa.String(length=_RESOURCE_TYPE_LENGTH),
        )
    with op.batch_alter_table("task_runs") as batch:
        batch.alter_column(
            "resource_type",
            type_=sa.String(length=_RESOURCE_TYPE_LENGTH),
        )
        batch.alter_column(
            "status",
            type_=sa.String(length=_TASK_STATUS_LENGTH),
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        return

    # Keep the downgrade enum capable of representing every ResourceType that
    # current WireLoft data can contain. Otherwise PostgreSQL would fail the
    # cast merely because a newer resource type has already been persisted.
    resource_type = sa.Enum(
        "SHOW",
        "SEASON",
        "EPISODE",
        "MOVIE",
        "MOVIE_EXTRA",
        "MEDIA_DOWNLOAD",
        "DOWNLOAD_PROFILE",
        "DOWNLOAD_PROFILE_SERIES",
        name="resourcetype",
    )
    task_status = sa.Enum(
        "SCHEDULED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "RETRY_SCHEDULED",
        name="taskstatus",
    )

    if dialect == "postgresql":
        bind = op.get_bind()
        resource_type.create(bind, checkfirst=True)
        task_status.create(bind, checkfirst=True)
        op.alter_column(
            "task_schedules",
            "resource_type",
            type_=resource_type,
            postgresql_using="resource_type::resourcetype",
        )
        op.alter_column(
            "task_runs",
            "resource_type",
            type_=resource_type,
            postgresql_using="resource_type::resourcetype",
        )
        op.alter_column(
            "task_runs",
            "status",
            type_=task_status,
            postgresql_using="status::taskstatus",
        )
        return

    with op.batch_alter_table("task_schedules") as batch:
        batch.alter_column("resource_type", type_=resource_type)
    with op.batch_alter_table("task_runs") as batch:
        batch.alter_column("resource_type", type_=resource_type)
        batch.alter_column("status", type_=task_status)
