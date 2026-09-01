"""Add episode type filters to stream profiles.

Revision ID: 9c6e2a4b7f31
Revises: f4c2b7d91a6e
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c6e2a4b7f31"
down_revision: Union[str, None] = "f4c2b7d91a6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_EPISODE_TYPES = ["ep", "aux"]


def _backfill_episode_types() -> None:
    connection = op.get_bind()

    stream_profiles = sa.table(
        "stream_profiles",
        sa.column("id", sa.Integer()),
        sa.column("show_id", sa.Integer()),
        sa.column("use_downloads", sa.Boolean()),
        sa.column("preferred_format", sa.String()),
        sa.column("ep_id_type_list", sa.JSON()),
    )
    download_profiles = sa.table(
        "download_profiles",
        sa.column("id", sa.Integer()),
        sa.column("show_id", sa.Integer()),
        sa.column("local_media_profile_id", sa.Integer()),
        sa.column("enable_profile", sa.Boolean()),
        sa.column("ep_id_type_list", sa.JSON()),
    )
    local_media_profiles = sa.table(
        "local_media_profiles",
        sa.column("id", sa.Integer()),
        sa.column("preferred_format", sa.String()),
    )

    profiles = connection.execute(sa.select(
        stream_profiles.c.id,
        stream_profiles.c.show_id,
        stream_profiles.c.use_downloads,
        stream_profiles.c.preferred_format,
    )).mappings().all()

    for profile in profiles:
        episode_types = list(_DEFAULT_EPISODE_TYPES)
        if profile["use_downloads"]:
            matching_types = connection.execute(
                sa.select(download_profiles.c.ep_id_type_list)
                .join(
                    local_media_profiles,
                    local_media_profiles.c.id == download_profiles.c.local_media_profile_id,
                )
                .where(
                    download_profiles.c.show_id == profile["show_id"],
                    local_media_profiles.c.preferred_format == profile["preferred_format"],
                )
                .order_by(
                    download_profiles.c.enable_profile.desc(),
                    download_profiles.c.id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if matching_types is not None:
                episode_types = list(matching_types)

        connection.execute(
            stream_profiles.update()
            .where(stream_profiles.c.id == profile["id"])
            .values(ep_id_type_list=episode_types)
        )


def upgrade() -> None:
    with op.batch_alter_table("stream_profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ep_id_type_list",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[\"ep\", \"aux\"]'"),
            )
        )

    _backfill_episode_types()


def downgrade() -> None:
    with op.batch_alter_table("stream_profiles", schema=None) as batch_op:
        batch_op.drop_column("ep_id_type_list")
