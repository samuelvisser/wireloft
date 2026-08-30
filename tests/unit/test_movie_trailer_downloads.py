from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_movie_profile_requires_an_item_specific_variable() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    with pytest.raises(ValidationError, match="Movie and movie-extra downloads could resolve to the same file"):
        LocalMediaProfileAPICreate(
            type="movie",
            name="Unsafe",
            output_template="/downloads/movies/{movie_title}/{movie_title}.ext",
            preferred_format="format_1080p",
        )

    profile = LocalMediaProfileAPICreate(
        type="movie",
        name="Safe",
        output_template="/downloads/movies/{movie_title}/{title}.ext",
        preferred_format="format_1080p",
    )
    assert profile.output_template.endswith("{{ title }}.ext")


def test_movie_profile_accepts_media_type_placeholder_without_suffix() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    profile = LocalMediaProfileAPICreate(
        type="movie",
        name="Typed",
        output_template="/downloads/movies/{movie_title}/{movie_title}-{media_type}.ext",
        preferred_format="format_1080p",
    )
    assert profile.output_template.endswith("{{ media_type }}.ext")


def test_movie_extra_output_uses_parent_movie_and_actual_media_fields(tmp_path: Path, monkeypatch) -> None:
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_movie_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="run-hide-fight",
        title="Run Hide Fight",
        extended_title="Run Hide Fight | A Daily Wire Original",
        dw_id="movie-123",
        author_name="DailyWire+",
        mature_rating="TV-MA",
        description=None,
        downloaded_date=None,
        duration=6720,
    )
    trailer = MovieExtra(
        uuid="trailer-uuid",
        type=MediaType.MOVIE_EXTRA.value,
        movie=movie,
        movie_extra_type="trailer",
        slug="run-hide-fight-official-trailer",
        title="Run Hide Fight | Official Trailer",
        dw_id="trailer-456",
        description=None,
        downloaded_date=None,
        duration=180,
    )

    result = resolve_movie_output_path(
        "/downloads/movies/{movie_title}/{title}-{dw_id}-{media_type}.ext",
        movie=movie,
        media_item=trailer,
        append_media_type_to_filename=False,
        extension="mp4",
    )

    assert result == (
        tmp_path
        / "movies"
        / "Run Hide Fight"
        / "Run Hide Fight _ Official Trailer-trailer-456-trailer.mp4"
    ).resolve()


def test_movie_extra_type_suffix_is_added_before_extension(tmp_path: Path, monkeypatch) -> None:
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_movie_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="movie",
        title="Movie",
        description=None,
        downloaded_date=None,
        duration=100,
    )
    interview = MovieExtra(
        uuid="interview-uuid",
        type=MediaType.MOVIE_EXTRA.value,
        movie=movie,
        movie_extra_type="interview",
        slug="interview",
        title="Cast Interview",
        description=None,
        downloaded_date=None,
        duration=10,
    )

    result = resolve_movie_output_path(
        "/downloads/movies/{movie_title}/{title}.ext",
        movie=movie,
        media_item=interview,
        append_media_type_to_filename=True,
        extension="mp4",
    )

    assert result == (tmp_path / "movies" / "Movie" / "Cast Interview-interview.mp4").resolve()


def test_scheduler_accepts_movie_extra_resource_type() -> None:
    from task_manager.scheduler.types import ResourceType

    assert ResourceType("movie_extra") is ResourceType.MOVIE_EXTRA


def test_download_view_uses_movie_extra_as_media_identity_and_movie_as_parent() -> None:
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.media_downloads.service import get_media_downloads_view
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieLocalMediaProfile
    from backend.db.models.media_download import MovieExtraMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        profile = MovieLocalMediaProfile(
            slug="movies",
            name="Movies",
            output_template="/downloads/movies/{movie_title}/{title}.ext",
            preferred_format="format_1080p",
            append_media_type_to_filename=True,
        )
        movie = Movie(
            uuid="movie-view-uuid",
            type=MediaType.MOVIE.value,
            slug="parent-movie",
            title="Parent Movie",
            description=None,
            downloaded_date=None,
            duration=100,
        )
        trailer = MovieExtra(
            uuid="trailer-view-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie=movie,
            movie_extra_type="trailer",
            slug="official-trailer",
            title="Official Trailer",
            description=None,
            downloaded_date=None,
            duration=10,
        )
        session.add_all([profile, movie, trailer])
        session.flush()
        session.add(MovieExtraMediaDownload(
            type=MediaType.MOVIE_EXTRA.value,
            media_item_id=trailer.id,
            local_media_profile_id=profile.id,
            download_status=MediaDownloadStatus.PENDING.value,
            file_path="/downloads/movies/Parent Movie/Official Trailer-trailer.ext",
            progress=0,
        ))
        session.commit()

        rows = get_media_downloads_view(session)

        assert len(rows) == 1
        assert rows[0].type == MediaType.MOVIE_EXTRA.value
        assert rows[0].movie_extra_type == "trailer"
        assert rows[0].media_slug == "official-trailer"
        assert rows[0].media_title == "Official Trailer"
        assert rows[0].movie_slug == "parent-movie"
        assert rows[0].movie_title == "Parent Movie"
    finally:
        session.close()
        engine.dispose()


def test_movie_extra_playback_uses_the_extras_own_slug() -> None:
    from types import SimpleNamespace

    from task_manager.tasks.workers.download_movie.service import _movie_extra_playback_url

    requested_slugs = []

    class FakeClient:
        @staticmethod
        def get_movie_extra_playback(slug):
            requested_slugs.append(slug)
            return SimpleNamespace(
                video_url="https://stream.example/interview.m3u8",
            )

    source_url = _movie_extra_playback_url(
        FakeClient(),
        movie=SimpleNamespace(id=1, slug="parent-movie", official_trailer_id=20),
        extra=SimpleNamespace(id=21, slug="cast-interview", title="Cast Interview"),
    )

    assert source_url == "https://stream.example/interview.m3u8"
    assert requested_slugs == ["cast-interview"]


def test_official_trailer_falls_back_to_parent_movie_playback() -> None:
    from types import SimpleNamespace

    from task_manager.tasks.workers.download_movie.service import _movie_extra_playback_url

    requested_slugs = []

    class FakeClient:
        @staticmethod
        def get_movie_extra_playback(slug):
            requested_slugs.append(("extra", slug))
            raise RuntimeError("Legacy trailer is unavailable from getClip")

        @staticmethod
        def get_movie_playback(slug):
            requested_slugs.append(("movie", slug))
            return SimpleNamespace(trailer_url="https://stream.example/trailer.m3u8")

    source_url = _movie_extra_playback_url(
        FakeClient(),
        movie=SimpleNamespace(id=1, slug="parent-movie", official_trailer_id=20),
        extra=SimpleNamespace(id=20, slug="official-trailer", title="Official Trailer"),
    )

    assert source_url == "https://stream.example/trailer.m3u8"
    assert requested_slugs == [
        ("extra", "official-trailer"),
        ("movie", "parent-movie"),
    ]
