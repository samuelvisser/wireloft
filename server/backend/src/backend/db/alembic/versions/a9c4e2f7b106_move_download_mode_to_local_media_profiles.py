"""Add configurable temporary download storage.

Revision ID: a9c4e2f7b106
Revises: f4d2a7b9c301
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a9c4e2f7b106"
down_revision = "f4d2a7b9c301"
branch_labels = None
depends_on = None

_OLD_PROFILE_INDEX = "uq_local_media_profiles_type_output_template_preferred_format"
_NEW_PROFILE_INDEX = "uq_local_media_profiles_type_template_format_mode"


def upgrade() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )
        batch.drop_index(_OLD_PROFILE_INDEX)
        batch.create_index(
            _NEW_PROFILE_INDEX,
            ["type", "output_template", "preferred_format", "download_mode"],
            unique=True,
        )


def downgrade() -> None:
    profiles = sa.table(
        "local_media_profiles",
        sa.column("type"),
        sa.column("output_template"),
        sa.column("preferred_format"),
    )
    duplicate_settings = op.get_bind().execute(
        sa.select(sa.literal(1))
        .select_from(profiles)
        .group_by(
            profiles.c.type,
            profiles.c.output_template,
            profiles.c.preferred_format,
        )
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate_settings is not None:
        raise RuntimeError(
            "Cannot downgrade while Local Media Profiles differ only by download behavior; "
            "remove or change the duplicate output settings first."
        )

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_index(_NEW_PROFILE_INDEX)
        batch.create_index(
            _OLD_PROFILE_INDEX,
            ["type", "output_template", "preferred_format"],
            unique=True,
        )
        batch.drop_column("download_mode")
