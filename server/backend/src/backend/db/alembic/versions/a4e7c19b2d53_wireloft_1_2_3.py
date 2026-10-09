"""Upgrade the shipped WireLoft 1.2.1 schema to WireLoft 1.2.3.

Revision ID: a4e7c19b2d53
Revises: f2a6c93d8b14
Create Date: 2026-10-09

This is the single release migration from WireLoft 1.2.1 to 1.2.3. The
latest prerelease revision is preserved so installations already migrated
through both development revisions remain at the current head.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a4e7c19b2d53"
down_revision = "f2a6c93d8b14"
branch_labels = None
depends_on = None


# Episode redownload intent -------------------------------------------------


def _upgrade_episode_redownload_intent() -> None:
    op.add_column(
        "media_downloads_episode",
        sa.Column(
            "redownload_when_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "media_downloads_episode",
        sa.Column(
            "redownload_when_delay_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Preserve the final-redownload intent of existing countdown downloads
    # whose originating profile requested a redownload after finalization.
    # The delay intent has no historical equivalent and defaults to false.
    op.get_bind().execute(
        sa.text(
            "UPDATE media_downloads_episode "
            "SET redownload_when_final = :enabled "
            "WHERE ("
            "downloaded_publish_status = :countdown_status "
            "OR id IN ("
            "SELECT md.id FROM media_downloads AS md "
            "JOIN media_items_episode AS e ON e.id = md.media_item_id "
            "WHERE e.publish_status = :countdown_status"
            ")"
            ") "
            "AND download_profile_id IN ("
            "SELECT id FROM download_profiles_podcast "
            "WHERE download_with_countdown = :enabled "
            "AND redownload_final = :enabled"
            ")"
        ),
        {
            "enabled": True,
            "countdown_status": "published_with_countdown",
        },
    )


def _downgrade_episode_redownload_intent() -> None:
    with op.batch_alter_table("media_downloads_episode") as batch:
        batch.drop_column("redownload_when_delay_passed")
        batch.drop_column("redownload_when_final")


# Release migration ---------------------------------------------------------


def upgrade() -> None:
    """Upgrade a shipped WireLoft 1.2.1 database directly to 1.2.3."""
    _upgrade_episode_redownload_intent()


def downgrade() -> None:
    """Return the WireLoft 1.2.3 schema to the shipped 1.2.1 schema."""
    _downgrade_episode_redownload_intent()
