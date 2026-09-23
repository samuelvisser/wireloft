from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


PREVIOUS_REVISION = "b6f3c8a1d2e4"
HEAD_REVISION = "c1a7e4d9b203"


def test_rss_output_mode_migration_rewrites_methods_and_stabilizes_feed_urls(
    tmp_path: Path,
    monkeypatch,
):
    from backend.db import core
    from backend.db.migrations import get_alembic_config

    database_path = tmp_path / "rss-output-mode-migration.db"
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

    cases = [
        ("stream_hls_download_m4a", "audio_hls"),
        ("stream_download_mp4", "mp4"),
        ("stream_hls_download_mp4", "mp4_hls"),
        # All former experiment-only values intentionally collapse back to the
        # supported default instead of becoming permanent runtime aliases.
        ("experiment_hls_local_mp4_or_dw", "audio_hls"),
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

            for index, (old_method, _new_mode) in enumerate(cases):
                profile_id = connection.execute(text(
                    "INSERT INTO stream_profiles "
                    "(type, show_id, enable_profile, token, use_downloads, "
                    "use_dw_stream, preferred_format, require_exact_match, ep_id_type_list) VALUES "
                    "('rss', :show_id, 1, :token, 1, 1, 'format_1080p', 0, '[]')"
                ), {
                    "show_id": show_id,
                    "token": f"profile-{index}",
                }).lastrowid
                connection.execute(text(
                    "INSERT INTO stream_profiles_rss "
                    "(id, feed_url, dw_video_method, max_items, "
                    "stream_live_episodes, live_episode_handoff_ids) VALUES "
                    "(:id, :feed_url, :method, 0, 0, '[]')"
                ), {
                    "id": profile_id,
                    "feed_url": (
                        f"https://wireloft.test/feed-{index}.xml?"
                        f"custom=value&dwVideoMethod={old_method}#fragment"
                    ),
                    "method": old_method,
                })

        command.upgrade(config, HEAD_REVISION)

        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT base.token, rss.video_output_mode, rss.feed_url "
                "FROM stream_profiles_rss AS rss "
                "JOIN stream_profiles AS base ON base.id = rss.id "
                "ORDER BY base.token"
            )).mappings().all()

        by_token = {row["token"]: row for row in rows}
        for index, (_old_method, new_mode) in enumerate(cases):
            row = by_token[f"profile-{index}"]
            assert row["video_output_mode"] == new_mode
            parts = urlsplit(row["feed_url"])
            assert parse_qs(parts.query) == {"custom": ["value"]}
            assert parts.fragment == "fragment"
    finally:
        engine.dispose()
