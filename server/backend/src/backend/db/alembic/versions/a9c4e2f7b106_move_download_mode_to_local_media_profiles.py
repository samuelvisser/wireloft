"""Move download storage mode to Local Media Profiles.

Revision ID: a9c4e2f7b106
Revises: f8a2d6c4b103
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a9c4e2f7b106"
down_revision = "f8a2d6c4b103"
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

    # Preserve the previous per-Download-Profile choice when all Download
    # Profiles pointing at one Local Media Profile agree. Conflicting old
    # overrides cannot be represented by the new model and safely fall back to
    # the system setting until the Local Media Profile is edited explicitly.
    bind = op.get_bind()
    download_profiles = sa.table(
        "download_profiles",
        sa.column("local_media_profile_id", sa.Integer()),
        sa.column("download_mode", sa.String()),
    )
    local_media_profiles = sa.table(
        "local_media_profiles",
        sa.column("id", sa.Integer()),
        sa.column("download_mode", sa.String()),
    )
    modes_by_profile: dict[int, set[str]] = {}
    for local_media_profile_id, download_mode in bind.execute(
        sa.select(
            download_profiles.c.local_media_profile_id,
            download_profiles.c.download_mode,
        )
    ):
        modes_by_profile.setdefault(local_media_profile_id, set()).add(download_mode)

    for local_media_profile_id, modes in modes_by_profile.items():
        if len(modes) != 1:
            continue
        bind.execute(
            sa.update(local_media_profiles)
            .where(local_media_profiles.c.id == local_media_profile_id)
            .values(download_mode=next(iter(modes)))
        )

    with op.batch_alter_table("download_profiles") as batch:
        batch.drop_column("download_mode")


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

    with op.batch_alter_table("download_profiles") as batch:
        batch.add_column(
            sa.Column(
                "download_mode",
                sa.String(length=16),
                nullable=False,
                server_default="system",
            )
        )

    bind = op.get_bind()
    download_profiles = sa.table(
        "download_profiles",
        sa.column("local_media_profile_id", sa.Integer()),
        sa.column("download_mode", sa.String()),
    )
    local_media_profiles = sa.table(
        "local_media_profiles",
        sa.column("id", sa.Integer()),
        sa.column("download_mode", sa.String()),
    )
    for local_media_profile_id, download_mode in bind.execute(
        sa.select(local_media_profiles.c.id, local_media_profiles.c.download_mode)
    ):
        bind.execute(
            sa.update(download_profiles)
            .where(download_profiles.c.local_media_profile_id == local_media_profile_id)
            .values(download_mode=download_mode)
        )

    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_index(_NEW_PROFILE_INDEX)
        batch.create_index(
            _OLD_PROFILE_INDEX,
            ["type", "output_template", "preferred_format"],
            unique=True,
        )
        batch.drop_column("download_mode")
