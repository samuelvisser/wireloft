"""Add first-run onboarding and WireLoft starter profiles.

Revision ID: c4ab8e7d1f20
Revises: b84c2d9e0f31
Create Date: 2026-08-30

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4ab8e7d1f20"
down_revision: Union[str, None] = "b84c2d9e0f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STARTER_PROFILES = (
    {
        "type": "show",
        "slug": "wireloft-shows-video",
        "name": "WireLoft Shows (Video)",
        "output_template": "/downloads/shows/{show_title}/{season_name}/{episode_title}.ext",
        "preferred_format": "format_1080p",
        "append_media_type_to_filename": True,
        "detail_table": "local_media_profiles_show",
    },
    {
        "type": "show",
        "slug": "wireloft-shows-audio",
        "name": "WireLoft Shows (Audio)",
        "output_template": "/downloads/podcasts/{show_title}/{episode_published_date} - {episode_title}.ext",
        "preferred_format": "format_audio_only",
        "append_media_type_to_filename": True,
        "detail_table": "local_media_profiles_show",
    },
    {
        "type": "movie",
        "slug": "wireloft-movies",
        "name": "WireLoft Movies",
        "output_template": "/downloads/movies/{movie_title}/{title}.ext",
        "preferred_format": "format_1080p",
        "append_media_type_to_filename": True,
        "detail_table": "local_media_profiles_movie",
    },
)


def _table_has_rows(bind: sa.Connection, table_name: str) -> bool:
    return bind.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).first() is not None


def _insert_starter_profile(bind: sa.Connection, profile: dict[str, object]) -> None:
    conflict = bind.execute(
        sa.text(
            "SELECT id FROM local_media_profiles "
            "WHERE slug = :slug OR name = :name "
            "OR (type = :type AND output_template = :output_template "
            "AND preferred_format = :preferred_format) "
            "LIMIT 1"
        ),
        profile,
    ).first()
    if conflict is not None:
        return

    result = bind.execute(
        sa.text(
            "INSERT INTO local_media_profiles "
            "(type, slug, name, output_template, preferred_format, append_media_type_to_filename) "
            "VALUES (:type, :slug, :name, :output_template, :preferred_format, "
            ":append_media_type_to_filename)"
        ),
        profile,
    )
    profile_id = result.lastrowid
    if profile_id is None:
        profile_id = bind.execute(
            sa.text("SELECT id FROM local_media_profiles WHERE slug = :slug"),
            {"slug": profile["slug"]},
        ).scalar_one()

    detail_table = str(profile["detail_table"])
    bind.execute(
        sa.text(f"INSERT INTO {detail_table} (id) VALUES (:id)"),
        {"id": profile_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    existing_installation = any(
        _table_has_rows(bind, table_name)
        for table_name in ("shows", "movies", "local_media_profiles")
    )

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "onboarding_completed",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    settings_exists = _table_has_rows(bind, "settings")
    if not settings_exists:
        bind.execute(
            sa.text("INSERT INTO settings (onboarding_completed) VALUES (:completed)"),
            {"completed": existing_installation},
        )
    elif existing_installation:
        bind.execute(sa.text("UPDATE settings SET onboarding_completed = :completed"), {"completed": True})

    for profile in _STARTER_PROFILES:
        _insert_starter_profile(bind, profile)


def downgrade() -> None:
    # Starter profiles are intentionally retained. They are valid user-editable records and
    # may already be referenced by downloads or download profiles when a downgrade occurs.
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("onboarding_completed")
