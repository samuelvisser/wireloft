"""Initial WireLoft schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TIMESTAMP_DEFAULT = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    op.create_table(
        "local_media_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("output_template", sa.String(), nullable=False),
        sa.Column("preferred_format", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_media_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_local_media_profiles_name")),
    )
    op.create_index(op.f("ix_local_media_profiles_slug"), "local_media_profiles", ["slug"], unique=True)

    op.create_table(
        "metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_table", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata")),
        sa.UniqueConstraint("parent_table", "parent_id", "key", name="uq_metadata_parent_key"),
    )
    op.create_index(op.f("ix_metadata_parent_id"), "metadata", ["parent_id"], unique=False)
    op.create_index("ix_metadata_parent", "metadata", ["parent_table", "parent_id"], unique=False)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )

    op.create_table(
        "shows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("sharing_url", sa.String(), nullable=False),
        sa.Column("membership_level", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("episode_identifier", sa.String(), nullable=False),
        sa.Column("author_name", sa.String(), nullable=False),
        sa.Column("author_slug", sa.String(), nullable=False),
        sa.Column("author_headshot_path", sa.String(), nullable=True),
        sa.Column("background_image_path", sa.String(), nullable=True),
        sa.Column("logo_image_path", sa.String(), nullable=True),
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shows")),
        sa.UniqueConstraint("sharing_url", name=op.f("uq_shows_sharing_url")),
    )
    op.create_index(op.f("ix_shows_slug"), "shows", ["slug"], unique=True)
    op.create_index(op.f("ix_shows_uuid"), "shows", ["uuid"], unique=True)

    op.create_table(
        "media_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("downloaded_date", sa.DateTime(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("background_image_path", sa.String(), nullable=True),
        sa.Column("thumbnail_landscape_path", sa.String(), nullable=True),
        sa.Column("thumbnail_portrait_path", sa.String(), nullable=True),
        sa.Column("thumbnail_square_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_items")),
    )
    op.create_index(op.f("ix_media_items_uuid"), "media_items", ["uuid"], unique=True)

    op.create_table(
        "task_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("allowed_resource_types", sa.JSON(), nullable=True),
        sa.Column("default_max_retries", sa.Integer(), nullable=True, comment="default max retries if not provided by schedule or trigger_now"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_definitions")),
    )
    op.create_index(op.f("ix_task_definitions_key"), "task_definitions", ["key"], unique=True)

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], name=op.f("fk_seasons_show_id_shows")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint("show_id", "index", name="uq_season_show_index"),
    )
    op.create_index(op.f("ix_seasons_slug"), "seasons", ["slug"], unique=True)

    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["media_items.id"], name=op.f("fk_movies_id_media_items"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movies")),
    )

    op.create_table(
        "download_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("enable_profile", sa.Boolean(), nullable=False),
        sa.Column("ep_id_type_list", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["local_media_profile_id"], ["local_media_profiles.id"], name=op.f("fk_download_profiles_local_media_profile_id_local_media_profiles")),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], name=op.f("fk_download_profiles_show_id_shows")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_profiles")),
        sa.UniqueConstraint("show_id", "local_media_profile_id", name="uq_unique_media_profile_per_show"),
    )

    op.create_table(
        "stream_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("enable_profile", sa.Boolean(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("use_downloads", sa.Boolean(), nullable=False, comment="Use local downloads for stream"),
        sa.Column("use_dw_stream", sa.Boolean(), nullable=False, comment="Use direct DW stream endpoints for stream"),
        sa.Column("preferred_format", sa.String(), nullable=False, comment="Preferred format for stream, used when choosing the correct downloaded file or whether to stream audio or video from DW"),
        sa.Column("require_exact_match", sa.Boolean(), nullable=False, comment="When allowing downloads, only allow exact matches for preferred format"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], name=op.f("fk_stream_profiles_show_id_shows")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_profiles")),
    )
    op.create_index(op.f("ix_stream_profiles_token"), "stream_profiles", ["token"], unique=True)

    resource_type_enum = sa.Enum(
        "SHOW",
        "SEASON",
        "EPISODE",
        "MOVIE",
        "DOWNLOAD_PROFILE",
        "DOWNLOAD_PROFILE_SERIES",
        name="resourcetype",
    )
    op.create_table(
        "task_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        sa.Column("scheduler_job_id", sa.String(), nullable=True, comment="APScheduler job id"),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", resource_type_enum, nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("trigger_args", sa.JSON(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("next_run_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=True, comment="Retry policy override for runs spawned by this schedule"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["task_definitions.id"], name=op.f("fk_task_schedules_definition_id_task_definitions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_schedules")),
    )
    op.create_index(op.f("ix_task_schedules_active"), "task_schedules", ["active"], unique=False)
    op.create_index(op.f("ix_task_schedules_definition_id"), "task_schedules", ["definition_id"], unique=False)
    op.create_index(op.f("ix_task_schedules_resource_id"), "task_schedules", ["resource_id"], unique=False)
    op.create_index(op.f("ix_task_schedules_resource_type"), "task_schedules", ["resource_type"], unique=False)
    op.create_index(op.f("ix_task_schedules_scheduler_job_id"), "task_schedules", ["scheduler_job_id"], unique=False)

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("episode_identifier", sa.String(), nullable=False, comment="Unique identifier that is used to identify the episode within the show"),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("publish_status", sa.String(), nullable=False),
        sa.Column("video_url", sa.String(), nullable=True),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("sharing_url", sa.String(), nullable=False),
        sa.Column("went_live_date", sa.DateTime(), nullable=True),
        sa.Column("published_date", sa.DateTime(), nullable=True),
        sa.Column("scheduled_date", sa.DateTime(), nullable=True),
        sa.Column("redownloaded_date", sa.DateTime(), nullable=True),
        sa.Column("is_no_show_today", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["media_items.id"], name=op.f("fk_episodes_id_media_items"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], name=op.f("fk_episodes_season_id_seasons")),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], name=op.f("fk_episodes_show_id_shows")),
        sa.PrimaryKeyConstraint("id", "show_id", name=op.f("pk_episodes")),
        sa.UniqueConstraint("show_id", "episode_identifier", name="uq_unique_episode_identifier_per_show"),
        sa.UniqueConstraint("show_id", "index", name="uq_episode_show_index"),
    )
    op.create_index(op.f("ix_episodes_slug"), "episodes", ["slug"], unique=True)

    op.create_table(
        "download_profiles_podcast",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("download_with_countdown", sa.Boolean(), nullable=False),
        sa.Column("redownload_final", sa.Boolean(), nullable=False),
        sa.Column("download_days_in_past", sa.Integer(), nullable=False),
        sa.Column("delete_older_episodes", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["download_profiles.id"], name=op.f("fk_download_profiles_podcast_id_download_profiles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_profiles_podcast")),
    )

    op.create_table(
        "download_profiles_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("include_upcoming_seasons", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["download_profiles.id"], name=op.f("fk_download_profiles_series_id_download_profiles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_profiles_series")),
    )

    op.create_table(
        "stream_profiles_rss",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feed_url", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["stream_profiles.id"], name=op.f("fk_stream_profiles_rss_id_stream_profiles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_profiles_rss")),
    )

    op.create_table(
        "media_downloads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("local_media_profile_id", sa.Integer(), nullable=False),
        sa.Column("download_status", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("downloaded_bytes", sa.Integer(), nullable=True),
        sa.Column("format_downloaded", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["local_media_profile_id"], ["local_media_profiles.id"], name=op.f("fk_media_downloads_local_media_profile_id_local_media_profiles")),
        sa.ForeignKeyConstraint(["media_item_id"], ["media_items.id"], name=op.f("fk_media_downloads_media_item_id_media_items")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads")),
        sa.UniqueConstraint("media_item_id", "local_media_profile_id", name="uq_download_per_media_profile"),
    )

    task_status_enum = sa.Enum(
        "SCHEDULED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
        "RETRY_SCHEDULED",
        name="taskstatus",
    )
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=True),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", resource_type_enum, nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("status", task_status_enum, nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["task_definitions.id"], name=op.f("fk_task_runs_definition_id_task_definitions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["task_schedules.id"], name=op.f("fk_task_runs_schedule_id_task_schedules"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_runs")),
    )
    op.create_index(op.f("ix_task_runs_definition_id"), "task_runs", ["definition_id"], unique=False)
    op.create_index(op.f("ix_task_runs_resource_id"), "task_runs", ["resource_id"], unique=False)
    op.create_index(op.f("ix_task_runs_resource_type"), "task_runs", ["resource_type"], unique=False)
    op.create_index(op.f("ix_task_runs_schedule_id"), "task_runs", ["schedule_id"], unique=False)
    op.create_index(op.f("ix_task_runs_status"), "task_runs", ["status"], unique=False)

    op.create_table(
        "download_profile_series_seasons",
        sa.Column("series_download_profile_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], name=op.f("fk_download_profile_series_seasons_season_id_seasons")),
        sa.ForeignKeyConstraint(["series_download_profile_id"], ["download_profiles_series.id"], name=op.f("fk_download_profile_series_seasons_series_download_profile_id_download_profiles_series")),
    )

    op.create_table(
        "media_downloads_episode",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("download_profile_id", sa.Integer(), nullable=True),
        sa.Column("downloaded_publish_status", sa.String(), nullable=True),
        sa.Column("is_redownload_attempt", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["download_profile_id"], ["download_profiles.id"], name=op.f("fk_media_downloads_episode_download_profile_id_download_profiles")),
        sa.ForeignKeyConstraint(["id"], ["media_downloads.id"], name=op.f("fk_media_downloads_episode_id_media_downloads"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_episode")),
    )

    op.create_table(
        "media_download_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_download_id", sa.Integer(), nullable=False),
        sa.Column("is_redownload", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("downloaded_bytes", sa.Integer(), nullable=True),
        sa.Column("format_downloaded", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_TIMESTAMP_DEFAULT, nullable=False),
        sa.ForeignKeyConstraint(["media_download_id"], ["media_downloads.id"], name=op.f("fk_media_download_attempts_media_download_id_media_downloads"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_download_attempts")),
    )
    op.create_index(op.f("ix_media_download_attempts_media_download_id"), "media_download_attempts", ["media_download_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_media_download_attempts_media_download_id"), table_name="media_download_attempts")
    op.drop_table("media_download_attempts")
    op.drop_table("media_downloads_episode")
    op.drop_table("download_profile_series_seasons")
    op.drop_index(op.f("ix_task_runs_status"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_schedule_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_resource_type"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_resource_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_definition_id"), table_name="task_runs")
    op.drop_table("task_runs")
    op.drop_table("media_downloads")
    op.drop_table("stream_profiles_rss")
    op.drop_table("download_profiles_series")
    op.drop_table("download_profiles_podcast")
    op.drop_index(op.f("ix_episodes_slug"), table_name="episodes")
    op.drop_table("episodes")
    op.drop_index(op.f("ix_task_schedules_scheduler_job_id"), table_name="task_schedules")
    op.drop_index(op.f("ix_task_schedules_resource_type"), table_name="task_schedules")
    op.drop_index(op.f("ix_task_schedules_resource_id"), table_name="task_schedules")
    op.drop_index(op.f("ix_task_schedules_definition_id"), table_name="task_schedules")
    op.drop_index(op.f("ix_task_schedules_active"), table_name="task_schedules")
    op.drop_table("task_schedules")
    op.drop_index(op.f("ix_stream_profiles_token"), table_name="stream_profiles")
    op.drop_table("stream_profiles")
    op.drop_table("download_profiles")
    op.drop_table("movies")
    op.drop_index(op.f("ix_seasons_slug"), table_name="seasons")
    op.drop_table("seasons")
    op.drop_index(op.f("ix_task_definitions_key"), table_name="task_definitions")
    op.drop_table("task_definitions")
    op.drop_index(op.f("ix_media_items_uuid"), table_name="media_items")
    op.drop_table("media_items")
    op.drop_index(op.f("ix_shows_uuid"), table_name="shows")
    op.drop_index(op.f("ix_shows_slug"), table_name="shows")
    op.drop_table("shows")
    op.drop_table("settings")
    op.drop_index("ix_metadata_parent", table_name="metadata")
    op.drop_index(op.f("ix_metadata_parent_id"), table_name="metadata")
    op.drop_table("metadata")
    op.drop_index(op.f("ix_local_media_profiles_slug"), table_name="local_media_profiles")
    op.drop_table("local_media_profiles")
