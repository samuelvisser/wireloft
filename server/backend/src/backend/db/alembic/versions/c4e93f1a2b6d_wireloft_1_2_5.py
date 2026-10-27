"""Upgrade the shipped WireLoft 1.2.4 schema to WireLoft 1.2.5.

Revision ID: c4e93f1a2b6d
Revises: a4e7c19b2d53
Create Date: 2026-10-27

This is the single release migration from WireLoft 1.2.4 to 1.2.5. It
combines the constraint and index renames with Local Media Profile subtitle
handling. The latest subtitle prerelease revision is preserved so
installations already migrated through it remain at the current head.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4e93f1a2b6d"
down_revision = "a4e7c19b2d53"
branch_labels = None
depends_on = None


# Constraint and index names ------------------------------------------------
# Tables renamed in earlier releases kept the index and constraint names of
# their old table, and the artifact identity check got its naming-convention
# prefix twice.

_IDENTITY_CHECK = (
    "artifact_status IN ('absent', 'missing') OR ("
    "artifact_stat_dev IS NOT NULL AND length(artifact_stat_dev) > 0 AND "
    "artifact_stat_ino IS NOT NULL AND length(artifact_stat_ino) > 0 AND "
    "artifact_size_bytes IS NOT NULL AND artifact_size_bytes >= 0 AND "
    "artifact_fingerprint IS NOT NULL AND length(artifact_fingerprint) = 64"
    ")"
)
_DOUBLED_IDENTITY_NAME = "ck_media_downloads_ck_media_downloads_artifact_identity_complete"
_IDENTITY_NAME = "ck_media_downloads_artifact_identity_complete"

# (table, old name, new name, columns, unique)
_INDEXES = (
    ("media_items_episode", "ix_episodes_slug", "ix_media_items_episode_slug", ["slug"], True),
    ("media_items_movie", "ix_movies_slug", "ix_media_items_movie_slug", ["slug"], True),
    ("media_items_movie_extra", "ix_movie_extras_movie_id", "ix_media_items_movie_extra_movie_id", ["movie_id"], False),
    ("media_items_movie_extra", "ix_movie_extras_source_id", "ix_media_items_movie_extra_source_id", ["source_id"], False),
)

# (table, old name, new name, columns)
_UNIQUE_CONSTRAINTS = (
    ("media_items_movie", "uq_movies_official_trailer_id", "uq_media_items_movie_official_trailer_id", ["official_trailer_id"]),
    ("media_items_movie_extra", "uq_movie_extras_movie_id_source_id", "uq_media_items_movie_extra_movie_id", ["movie_id", "source_id"]),
)


def _rename_indexes(*, reverse: bool) -> None:
    for table, old, new, columns, unique in _INDEXES:
        current, wanted = (new, old) if reverse else (old, new)
        op.drop_index(op.f(current), table_name=table)
        op.create_index(op.f(wanted), table, columns, unique=unique)


def _rename_unique_constraints(*, reverse: bool) -> None:
    for table, old, new, columns in _UNIQUE_CONSTRAINTS:
        current, wanted = (new, old) if reverse else (old, new)
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(op.f(current), type_="unique")
            batch.create_unique_constraint(op.f(wanted), columns)


def _upgrade_schema_names() -> None:
    _rename_indexes(reverse=False)
    _rename_unique_constraints(reverse=False)
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_constraint(op.f(_DOUBLED_IDENTITY_NAME), type_="check")
        batch.create_check_constraint(op.f(_IDENTITY_NAME), _IDENTITY_CHECK)


def _downgrade_schema_names() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_constraint(op.f(_IDENTITY_NAME), type_="check")
        batch.create_check_constraint(op.f(_DOUBLED_IDENTITY_NAME), _IDENTITY_CHECK)
    _rename_unique_constraints(reverse=True)
    _rename_indexes(reverse=True)


# Local Media Profile subtitle handling -------------------------------------


def _upgrade_subtitle_mode() -> None:
    op.add_column(
        "local_media_profiles",
        sa.Column("subtitle_mode", sa.String(length=24), nullable=False, server_default="no_subtitles"),
    )
    # Movie profiles and show profiles covering series acquire subtitles as a
    # sidecar on their next download; podcast-only show profiles do not.
    op.execute(sa.text("""
        UPDATE local_media_profiles
        SET subtitle_mode = 'sidecar'
        WHERE type = 'movie' OR (type = 'show' AND id IN (
            SELECT id FROM local_media_profiles_show
            WHERE show_scope IN ('series', 'both')
        ))
    """))
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.alter_column(
            "subtitle_mode",
            existing_type=sa.String(length=24),
            existing_nullable=False,
            server_default="sidecar",
        )


def _downgrade_subtitle_mode() -> None:
    with op.batch_alter_table("local_media_profiles") as batch:
        batch.drop_column("subtitle_mode")


# Release migration ---------------------------------------------------------


def upgrade() -> None:
    _upgrade_schema_names()
    _upgrade_subtitle_mode()


def downgrade() -> None:
    _downgrade_subtitle_mode()
    _downgrade_schema_names()
