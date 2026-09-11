from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


PREVIOUS_REVISION = "f4d2a7b9c301"
HEAD_REVISION = "a9c4e7b2d610"


def test_rss_video_method_migration_canonicalizes_existing_values(
    tmp_path: Path,
    monkeypatch,
):
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "rss-video-method-migration.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    config = get_alembic_config(allow_version_storage_migration=True)
    command.upgrade(config, PREVIOUS_REVISION)

    method_cases = [
        ("podcasting_2_0", "stream_hls_download_m4a"),
        ("cached_mp4", "stream_download_mp4"),
        ("podcasting_2_0_cached_mp4", "stream_hls_download_mp4"),
    ]

    try:
        with engine.begin() as connection:
            show_id = connection.execute(text(
                "INSERT INTO shows "
                "(uuid, slug, title, description, sharing_url, membership_level, "
                "type, episode_identifier, author_name, author_slug) VALUES "
                "('migration-show-uuid', 'migration-show', 'Migration Show', "
                "'Description', 'https://example.test/migration-show', 'FREE', "
                "'podcast', 'numbered', 'Host', 'host')"
            )).lastrowid

            for index, (legacy_method, _canonical_method) in enumerate(method_cases):
                profile_id = connection.execute(text(
                    "INSERT INTO stream_profiles "
                    "(type, show_id, enable_profile, token, use_downloads, "
                    "use_dw_stream, preferred_format, require_exact_match) VALUES "
                    "('rss', :show_id, 1, :token, 0, 1, 'format_1080p', 0)"
                ), {
                    "show_id": show_id,
                    "token": f"legacy-{index}",
                }).lastrowid
                connection.execute(text(
                    "INSERT INTO stream_profiles_rss "
                    "(id, feed_url, dw_video_method, max_items) VALUES "
                    "(:id, :feed_url, :method, 0)"
                ), {
                    "id": profile_id,
                    "feed_url": (
                        f"https://wireloft.test/feed-{index}.xml?"
                        f"custom=value&dwVideoMethod={legacy_method}#fragment"
                    ),
                    "method": legacy_method,
                })

        command.upgrade(config, HEAD_REVISION)

        with engine.connect() as connection:
            profiles = connection.execute(text(
                "SELECT base.token, rss.dw_video_method, rss.feed_url "
                "FROM stream_profiles_rss AS rss "
                "JOIN stream_profiles AS base ON base.id = rss.id "
                "ORDER BY base.token"
            )).mappings().all()

        profiles_by_token = {profile["token"]: profile for profile in profiles}
        for index, (_legacy_method, canonical_method) in enumerate(method_cases):
            profile = profiles_by_token[f"legacy-{index}"]
            assert profile["dw_video_method"] == canonical_method
            parts = urlsplit(profile["feed_url"])
            assert parse_qs(parts.query) == {
                "custom": ["value"],
                "dwVideoMethod": [canonical_method],
            }
            assert parts.fragment == "fragment"
    finally:
        engine.dispose()
