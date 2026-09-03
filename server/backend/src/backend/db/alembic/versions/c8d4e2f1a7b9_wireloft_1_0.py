"""WireLoft 1.0.

Revision ID: c8d4e2f1a7b9
Revises: 0001
Create Date: 2026-09-03

This is the single release migration from the schema shipped on ``main`` to
WireLoft 1.0. The 0001 baseline intentionally describes the unmanaged main
schema exactly; all schema and data changes made on develop are consolidated
here.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Sequence, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
from config.settings.base import get_config_path
from jinja2 import Environment
import sqlalchemy as sa


revision: str = "c8d4e2f1a7b9"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_EPISODE_TYPES = ["ep", "aux"]
_RSS_QUERY_PARAMETER = "dwVideoMethod"
_RSS_VIDEO_METHOD = "stream_hls_download_m4a"

_LEGACY_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
_JINJA_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_MEDIA_TYPE_SUFFIX = "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}"
_DATE_FIELDS = (
    "date",
    "time",
    "datetime",
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
)
_MOVIE_TEMPLATE_UPGRADE_VARIABLES = {
    "movie": "movie_slug",
    **{field: f"movie_{field}" for field in _DATE_FIELDS},
}
_MOVIE_TEMPLATE_DOWNGRADE_VARIABLES = {
    f"movie_{field}": field for field in _DATE_FIELDS
}

_DOWNLOAD_SETTINGS_SECTION = re.compile(
    r"^(?P<indent>\s*)(?:downloadSettings|download_settings)\s*:\s*(?:#.*)?$"
)
_LEGACY_FILENAME_SETTING = re.compile(
    r"^(?P<indent>\s*)(?:asciiOnlyFilenames|ascii_only_filenames)\s*:"
)
_CURRENT_FILENAME_SETTING = re.compile(
    r"^(?P<indent>\s*)(?:filenameRestrictionMode|filename_restriction_mode)\s*:"
)

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


def upgrade() -> None:
    # The first develop migration rejected duplicate legacy profile settings
    # before touching the schema. Keep that all-or-nothing behaviour now that
    # the whole release is one revision.
    _raise_for_duplicate_legacy_profile_settings()

    _upgrade_movies_from_main()
    _upgrade_local_media_profiles()
    _upgrade_download_tracking()
    _upgrade_movie_extras()
    _upgrade_onboarding()
    _upgrade_output_templates_to_jinja()
    _upgrade_rss_profiles()
    _upgrade_podcast_download_limits()
    _upgrade_stream_profile_episode_types()
    _upgrade_movie_template_variables()
    _allow_shared_download_media_profiles()
    _migrate_config(_upgrade_config_text)
    _upgrade_episode_metadata_finality()


def downgrade() -> None:
    _downgrade_episode_metadata_finality()
    _migrate_config(_downgrade_config_text)
    _restore_download_media_profile_uniqueness()
    _downgrade_movie_template_variables()
    _downgrade_stream_profile_episode_types()
    _downgrade_podcast_download_limits()
    _downgrade_rss_profiles()
    _downgrade_output_templates_from_jinja()
    _downgrade_onboarding()
    _downgrade_movie_extras()
    _downgrade_download_tracking()
    _downgrade_local_media_profiles()
    _downgrade_movies_to_main()


def _raise_for_duplicate_legacy_profile_settings() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "SELECT output_template, preferred_format, COUNT(*) AS profile_count "
        "FROM local_media_profiles "
        "GROUP BY output_template, preferred_format "
        "HAVING COUNT(*) > 1 "
        "LIMIT 1"
    )).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "Local Media Profiles must be unique by type, output template, and "
            "preferred format before this migration can continue; found "
            f"{duplicate['profile_count']} duplicate Show profiles using output "
            f"template '{duplicate['output_template']}' and preferred format "
            f"'{duplicate['preferred_format']}'."
        )


def _upgrade_movies_from_main() -> None:
    # These fields and the movie download subtype were added on develop before
    # Alembic was introduced. They used to be folded into 0001, which made the
    # baseline newer than the database shipped on main.
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extended_title", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("dw_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("sharing_url", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("author_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("author_slug", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("logo_image_path", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("mature_rating", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_downloadable", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column(
            "available_for",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ))
        batch_op.add_column(sa.Column("release_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("release_date_source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("release_date_source_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column(
            "release_date_lookup_status",
            sa.String(),
            server_default="pending",
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "release_date_lookup_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ))
        batch_op.add_column(sa.Column("release_date_lookup_error", sa.String(), nullable=True))
        batch_op.create_index(batch_op.f("ix_movies_dw_id"), ["dw_id"], unique=True)

    op.create_table(
        "media_downloads_movie",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_downloads.id"],
            name=op.f("fk_media_downloads_movie_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_movie")),
    )


def _downgrade_movies_to_main() -> None:
    op.drop_table("media_downloads_movie")
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_movies_dw_id"))
        batch_op.drop_column("release_date_lookup_error")
        batch_op.drop_column("release_date_lookup_attempted_at")
        batch_op.drop_column("release_date_lookup_status")
        batch_op.drop_column("release_date_source_id")
        batch_op.drop_column("release_date_source")
        batch_op.drop_column("release_date")
        batch_op.drop_column("available_for")
        batch_op.drop_column("is_downloadable")
        batch_op.drop_column("mature_rating")
        batch_op.drop_column("logo_image_path")
        batch_op.drop_column("author_slug")
        batch_op.drop_column("author_name")
        batch_op.drop_column("sharing_url")
        batch_op.drop_column("dw_id")
        batch_op.drop_column("extended_title")


def _upgrade_local_media_profiles() -> None:
    op.create_table(
        "local_media_profiles_movie",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["local_media_profiles.id"],
            name=op.f("fk_local_media_profiles_movie_id_local_media_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_media_profiles_movie")),
    )
    op.create_table(
        "local_media_profiles_show",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["local_media_profiles.id"],
            name=op.f("fk_local_media_profiles_show_id_local_media_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_media_profiles_show")),
    )

    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "type",
            sa.String(),
            server_default="show",
            nullable=False,
        ))

    op.execute(sa.text(
        "INSERT INTO local_media_profiles_show (id) "
        "SELECT id FROM local_media_profiles WHERE type = 'show'"
    ))

    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.create_index(
            "uq_local_media_profiles_type_output_template_preferred_format",
            ["type", "output_template", "preferred_format"],
            unique=True,
        )
        batch_op.add_column(sa.Column(
            "append_media_type_to_filename",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ))


def _downgrade_local_media_profiles() -> None:
    op.drop_table("local_media_profiles_show")
    op.drop_table("local_media_profiles_movie")
    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_local_media_profiles_type_output_template_preferred_format"
        )
        batch_op.drop_column("append_media_type_to_filename")
        batch_op.drop_column("type")


def _upgrade_download_tracking() -> None:
    with op.batch_alter_table("media_downloads", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "attempt_generation",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ))


def _downgrade_download_tracking() -> None:
    with op.batch_alter_table("media_downloads", schema=None) as batch_op:
        batch_op.drop_column("attempt_generation")


def _upgrade_movie_extras() -> None:
    op.create_table(
        "movie_extras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("movie_extra_type", sa.String(), server_default="other", nullable=False),
        sa.Column("dw_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("sharing_url", sa.String(), nullable=True),
        sa.Column("published_date", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_items.id"],
            name=op.f("fk_movie_extras_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_movie_extras_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movie_extras")),
    )
    with op.batch_alter_table("movie_extras", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_movie_extras_dw_id"), ["dw_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_movie_extras_movie_id"), ["movie_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_movie_extras_slug"), ["slug"], unique=True)

    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("official_trailer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_movies_official_trailer_id_movie_extras"),
            "movie_extras",
            ["official_trailer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_movies_official_trailer_id"),
            ["official_trailer_id"],
        )

    op.create_table(
        "media_downloads_movie_extra",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["media_downloads.id"],
            name=op.f("fk_media_downloads_movie_extra_id_media_downloads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_downloads_movie_extra")),
    )


def _downgrade_movie_extras() -> None:
    connection = op.get_bind()
    movie_extra_ids = [
        row[0]
        for row in connection.execute(sa.text(
            "SELECT id FROM movie_extras ORDER BY id"
        ))
    ]

    # Main has no MovieExtra subtype. Remove its dependent download rows before
    # deleting the media items so foreign-key enforcement cannot strand data.
    connection.execute(sa.text(
        "DELETE FROM media_downloads "
        "WHERE media_item_id IN (SELECT id FROM movie_extras)"
    ))

    op.drop_table("media_downloads_movie_extra")
    with op.batch_alter_table("movies", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("uq_movies_official_trailer_id"),
            type_="unique",
        )
        batch_op.drop_constraint(
            batch_op.f("fk_movies_official_trailer_id_movie_extras"),
            type_="foreignkey",
        )
        batch_op.drop_column("official_trailer_id")
    op.drop_table("movie_extras")

    for movie_extra_id in movie_extra_ids:
        connection.execute(
            sa.text("DELETE FROM media_items WHERE id = :id"),
            {"id": movie_extra_id},
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


def _upgrade_onboarding() -> None:
    bind = op.get_bind()
    existing_installation = any(
        _table_has_rows(bind, table_name)
        for table_name in ("shows", "movies", "local_media_profiles")
    )

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ))

    settings_exists = _table_has_rows(bind, "settings")
    if not settings_exists:
        bind.execute(
            sa.text("INSERT INTO settings (onboarding_completed) VALUES (:completed)"),
            {"completed": existing_installation},
        )
    elif existing_installation:
        bind.execute(
            sa.text("UPDATE settings SET onboarding_completed = :completed"),
            {"completed": True},
        )

    for profile in _STARTER_PROFILES:
        _insert_starter_profile(bind, profile)


def _downgrade_onboarding() -> None:
    # Keep starter profiles, matching the original migration. They are valid
    # user-editable rows and may already be referenced when downgrading.
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("onboarding_completed")


def _upgrade_output_templates_to_jinja() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, type, output_template, append_media_type_to_filename "
        "FROM local_media_profiles"
    )).mappings()

    for profile in profiles:
        output_template = _LEGACY_PLACEHOLDER.sub(
            lambda match: "{{ " + match.group(1) + " }}",
            profile["output_template"],
        )
        if (
            profile["type"] == "movie"
            and profile["append_media_type_to_filename"]
            and output_template.endswith(".ext")
        ):
            output_template = output_template[:-4] + _MEDIA_TYPE_SUFFIX + ".ext"
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles "
                "SET output_template = :output_template, append_media_type_to_filename = 0 "
                "WHERE id = :profile_id"
            ),
            {"output_template": output_template, "profile_id": profile["id"]},
        )

    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.alter_column(
            "append_media_type_to_filename",
            existing_type=sa.Boolean(),
            server_default=sa.false(),
            existing_nullable=False,
        )


def _downgrade_output_templates_from_jinja() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, output_template FROM local_media_profiles"
    )).mappings()

    for profile in profiles:
        output_template = profile["output_template"]
        had_legacy_suffix = output_template.endswith(_MEDIA_TYPE_SUFFIX + ".ext")
        if had_legacy_suffix:
            output_template = output_template[:-(len(_MEDIA_TYPE_SUFFIX) + 4)] + ".ext"
        output_template = _JINJA_VARIABLE.sub(
            lambda match: "{" + match.group(1) + "}",
            output_template,
        )
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles "
                "SET output_template = :output_template, append_media_type_to_filename = :append_suffix "
                "WHERE id = :profile_id"
            ),
            {
                "output_template": output_template,
                "append_suffix": 1 if had_legacy_suffix else 0,
                "profile_id": profile["id"],
            },
        )

    with op.batch_alter_table("local_media_profiles", schema=None) as batch_op:
        batch_op.alter_column(
            "append_media_type_to_filename",
            existing_type=sa.Boolean(),
            server_default=sa.true(),
            existing_nullable=False,
        )


def _set_rss_method(feed_url: str, method: str | None) -> str:
    parts = urlsplit(feed_url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != _RSS_QUERY_PARAMETER
    ]
    if method is not None:
        query.append((_RSS_QUERY_PARAMETER, method))
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def _upgrade_rss_profiles() -> None:
    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "dw_video_method",
            sa.String(),
            nullable=False,
            server_default=_RSS_VIDEO_METHOD,
        ))
        batch_op.add_column(sa.Column(
            "max_items",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ))

    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT rss.id, rss.feed_url, base.use_dw_stream "
        "FROM stream_profiles_rss AS rss "
        "JOIN stream_profiles AS base ON base.id = rss.id"
    )).mappings()
    for profile in profiles:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss "
                "SET dw_video_method = :method, feed_url = :feed_url "
                "WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "method": _RSS_VIDEO_METHOD,
                "feed_url": _set_rss_method(
                    profile["feed_url"],
                    _RSS_VIDEO_METHOD if profile["use_dw_stream"] else None,
                ),
            },
        )


def _downgrade_rss_profiles() -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, feed_url FROM stream_profiles_rss"
    )).mappings()
    for profile in profiles:
        connection.execute(
            sa.text(
                "UPDATE stream_profiles_rss SET feed_url = :feed_url WHERE id = :id"
            ),
            {
                "id": profile["id"],
                "feed_url": _set_rss_method(profile["feed_url"], None),
            },
        )

    with op.batch_alter_table("stream_profiles_rss", schema=None) as batch_op:
        batch_op.drop_column("max_items")
        batch_op.drop_column("dw_video_method")


def _upgrade_podcast_download_limits() -> None:
    with op.batch_alter_table("download_profiles_podcast", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "download_episode_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ))


def _downgrade_podcast_download_limits() -> None:
    with op.batch_alter_table("download_profiles_podcast", schema=None) as batch_op:
        batch_op.drop_column("download_episode_count")


def _upgrade_stream_profile_episode_types() -> None:
    with op.batch_alter_table("stream_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "ep_id_type_list",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[\"ep\", \"aux\"]'"),
        ))
    _backfill_stream_profile_episode_types()


def _backfill_stream_profile_episode_types() -> None:
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


def _downgrade_stream_profile_episode_types() -> None:
    with op.batch_alter_table("stream_profiles", schema=None) as batch_op:
        batch_op.drop_column("ep_id_type_list")


def _rewrite_jinja_names(template: str, replacements: dict[str, str]) -> str:
    environment = Environment()
    return "".join(
        replacements.get(value, value) if token_type == "name" else value
        for _line, token_type, value in environment.lex(template)
    )


def _rewrite_movie_profiles(replacements: dict[str, str]) -> None:
    connection = op.get_bind()
    profiles = connection.execute(sa.text(
        "SELECT id, output_template FROM local_media_profiles WHERE type = 'movie'"
    )).mappings()
    for profile in profiles:
        connection.execute(
            sa.text(
                "UPDATE local_media_profiles SET output_template = :output_template "
                "WHERE id = :profile_id"
            ),
            {
                "output_template": _rewrite_jinja_names(
                    profile["output_template"],
                    replacements,
                ),
                "profile_id": profile["id"],
            },
        )


def _upgrade_movie_template_variables() -> None:
    _rewrite_movie_profiles(_MOVIE_TEMPLATE_UPGRADE_VARIABLES)


def _downgrade_movie_template_variables() -> None:
    _rewrite_movie_profiles(_MOVIE_TEMPLATE_DOWNGRADE_VARIABLES)


def _allow_shared_download_media_profiles() -> None:
    with op.batch_alter_table("download_profiles", schema=None) as batch_op:
        batch_op.drop_constraint("uq_unique_media_profile_per_show", type_="unique")


def _restore_download_media_profile_uniqueness() -> None:
    with op.batch_alter_table("download_profiles", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_unique_media_profile_per_show",
            ["show_id", "local_media_profile_id"],
        )


def _find_download_setting_lines(text: str) -> tuple[list[str], list[int], list[int]]:
    lines = text.splitlines(keepends=True)
    section_indent: int | None = None
    legacy_indexes: list[int] = []
    current_indexes: list[int] = []

    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(content) - len(content.lstrip())
        if section_indent is None:
            section = _DOWNLOAD_SETTINGS_SECTION.match(content)
            if section:
                section_indent = len(section.group("indent"))
            continue

        if indent <= section_indent:
            break
        if _LEGACY_FILENAME_SETTING.match(content):
            legacy_indexes.append(index)
        elif _CURRENT_FILENAME_SETTING.match(content):
            current_indexes.append(index)

    return lines, legacy_indexes, current_indexes


def _replace_line(line: str, *, key: str, value: str) -> str:
    content = line.rstrip("\r\n")
    newline = line[len(content):]
    indent = content[:len(content) - len(content.lstrip())]
    return f"{indent}{key}: {value}{newline}"


def _upgrade_config_text(text: str) -> str:
    lines, legacy_indexes, current_indexes = _find_download_setting_lines(text)
    if not legacy_indexes:
        return text

    if current_indexes:
        for index in reversed(legacy_indexes):
            del lines[index]
        return "".join(lines)

    first = legacy_indexes[0]
    lines[first] = _replace_line(
        lines[first],
        key="filenameRestrictionMode",
        value="windows",
    )
    for index in reversed(legacy_indexes[1:]):
        del lines[index]
    return "".join(lines)


def _downgrade_config_text(text: str) -> str:
    lines, legacy_indexes, current_indexes = _find_download_setting_lines(text)
    if legacy_indexes or not current_indexes:
        return text

    first = current_indexes[0]
    lines[first] = _replace_line(
        lines[first],
        key="asciiOnlyFilenames",
        value="true",
    )
    for index in reversed(current_indexes[1:]):
        del lines[index]
    return "".join(lines)


def _write_if_changed(path: Path, original: str, updated: str) -> None:
    if updated == original:
        return

    file_mode = path.stat().st_mode & 0o777
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.write(updated)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, file_mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _migrate_config(transform) -> None:
    path = get_config_path()
    try:
        original = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    _write_if_changed(path, original, transform(original))


def _upgrade_episode_metadata_finality() -> None:
    op.add_column(
        "episodes",
        sa.Column(
            "metadata_is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def _downgrade_episode_metadata_finality() -> None:
    op.drop_column("episodes", "metadata_is_final")
