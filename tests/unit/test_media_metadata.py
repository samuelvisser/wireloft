from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest


def _episode(*, identifier: str = "numbered"):
    show = SimpleNamespace(
        title="The Example Show",
        author_name="Example Host",
        episode_identifier=identifier,
    )
    season = SimpleNamespace(season_number=3)
    episode = SimpleNamespace(
        title="An Episode",
        description="Episode description",
        slug="an-episode",
        uuid="episode-uuid",
        sharing_url="https://example.test/episode",
        published_date=datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc),
        went_live_date=None,
        scheduled_date=None,
        duration=1800.0,
        season=season,
        episode_number="7",
    )
    return episode, show


def test_episode_metadata_keeps_real_season_and_episode_numbers():
    from task_manager.tasks.helpers.downloads.media_metadata import build_episode_metadata

    episode, show = _episode()
    metadata = build_episode_metadata(episode, show)

    assert metadata.show_title == "The Example Show"
    assert metadata.season_number == 3
    assert metadata.episode_number == 7
    assert metadata.aired == date(2026, 9, 28)
    assert metadata.ffmpeg_tags()["episode_sort"] == "7"


def test_date_based_episode_metadata_does_not_invent_numbers():
    from task_manager.tasks.helpers.downloads.media_metadata import build_episode_metadata

    episode, show = _episode(identifier="date_based")
    metadata = build_episode_metadata(episode, show)

    assert metadata.season_number is None
    assert metadata.episode_number is None
    assert "season_number" not in metadata.ffmpeg_tags()
    assert "episode_sort" not in metadata.ffmpeg_tags()


def test_movie_nfo_contains_media_server_metadata(tmp_path):
    from task_manager.tasks.helpers.downloads.media_metadata import (
        build_movie_metadata,
        write_nfo,
    )

    movie = SimpleNamespace(
        title="Example Movie",
        description="Movie description",
        slug="example-movie",
        uuid="movie-uuid",
        sharing_url="https://example.test/movie",
        release_date=date(2025, 6, 12),
        published_at=None,
        duration=7200.0,
        author_name="Producer",
        genres=[{"name": "Documentary"}, "Drama"],
        directed_by=["Director One"],
        written_by=["Writer One"],
        starring=["Actor One", "Actor Two"],
        cast_and_crew=[],
        production_companies=[{"name": "Example Studio"}],
        language="en",
        origin_country="US",
        mature_rating="PG-13",
    )
    media_path = tmp_path / "Example Movie.mp4"
    media_path.write_bytes(b"media")

    metadata = build_movie_metadata(movie, movie)
    nfo_path = write_nfo(str(media_path), metadata)
    root = ET.parse(nfo_path).getroot()

    assert root.tag == "movie"
    assert root.findtext("title") == "Example Movie"
    assert root.findtext("year") == "2025"
    assert root.findtext("mpaa") == "PG-13"
    assert [node.text for node in root.findall("genre")] == ["Documentary", "Drama"]
    assert [node.text for node in root.findall("director")] == ["Director One"]
    assert [node.findtext("name") for node in root.findall("actor")] == [
        "Actor One",
        "Actor Two",
    ]
    assert root.findtext("studio") == "Example Studio"


def test_nfo_writer_refuses_to_overwrite_external_file(tmp_path):
    from task_manager.tasks.helpers.downloads.media_metadata import (
        MediaServerMetadata,
        write_nfo,
    )

    media_path = tmp_path / "episode.mp4"
    media_path.write_bytes(b"media")
    nfo_path = tmp_path / "episode.nfo"
    nfo_path.write_text("external", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_nfo(
            str(media_path),
            MediaServerMetadata(kind="episode", title="Episode"),
        )

    assert nfo_path.read_text(encoding="utf-8") == "external"


def test_ffmpeg_metadata_embedding_stream_copies_media(tmp_path, monkeypatch):
    from dailywire_downloader import ffmpeg as ffmpeg_module

    media = tmp_path / "episode.mp4"
    media.write_bytes(b"media")
    commands: list[list[str]] = []

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    class Completed:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"tagged")
        return Completed()

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    ffmpeg_module.embed_metadata(
        str(media),
        {"title": "Episode title", "show": "Example Show"},
    )

    assert media.read_bytes() == b"tagged"
    command = commands[0]
    assert command[command.index("-c") + 1] == "copy"
    assert "title=Episode title" in command
    assert "show=Example Show" in command
    assert command[command.index("-f") + 1] == "mp4"


def test_metadata_mode_helpers_match_requested_outputs():
    from config.settings.submodels import MetadataMode
    from task_manager.tasks.helpers.downloads.media_metadata import (
        wants_metadata_embed,
        wants_metadata_nfo,
    )

    assert not wants_metadata_embed(MetadataMode.NO_METADATA)
    assert not wants_metadata_nfo(MetadataMode.NO_METADATA)

    assert wants_metadata_embed(MetadataMode.EMBED)
    assert not wants_metadata_nfo(MetadataMode.EMBED)

    assert not wants_metadata_embed(MetadataMode.NFO)
    assert wants_metadata_nfo(MetadataMode.NFO)

    assert wants_metadata_embed(MetadataMode.EMBED_AND_NFO)
    assert wants_metadata_nfo(MetadataMode.EMBED_AND_NFO)


def test_remove_download_artifacts_removes_tracked_nfo(tmp_path):
    from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts

    media = tmp_path / "episode.mp4"
    nfo = tmp_path / "episode.nfo"
    media.write_bytes(b"media")
    nfo.write_text("<episodedetails />", encoding="utf-8")

    remove_download_artifacts(str(media), nfo_path=str(nfo))

    assert not media.exists()
    assert not nfo.exists()
