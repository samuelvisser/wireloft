from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_tmdb_client_uses_runtime_to_choose_the_definitive_title_match(monkeypatch):
    from backend.integrations.tmdb import TMDbClient

    client = TMDbClient(access_token="test-token")
    payloads = {
        "/search/movie": {
            "results": [
                {
                    "id": 10,
                    "title": "Run Hide Fight",
                    "original_title": "Run Hide Fight",
                    "overview": "A student fights attackers at her high school.",
                    "popularity": 20,
                },
                {
                    "id": 20,
                    "title": "Run Hide Fight",
                    "original_title": "Run Hide Fight",
                    "overview": "An unrelated short film.",
                    "popularity": 100,
                },
            ]
        },
        "/movie/10": {
            "id": 10,
            "title": "Run Hide Fight",
            "original_title": "Run Hide Fight",
            "overview": "A student fights attackers at her high school.",
            "runtime": 109,
            "release_date": "2020-09-10",
        },
        "/movie/20": {
            "id": 20,
            "title": "Run Hide Fight",
            "original_title": "Run Hide Fight",
            "overview": "An unrelated short film.",
            "runtime": 74,
            "release_date": "2018-01-01",
        },
    }
    monkeypatch.setattr(client, "_get_json", lambda path, params=None: payloads[path])

    result = client.lookup_movie(
        title="Run Hide Fight",
        description="A student fights attackers at her high school.",
        duration_seconds=109 * 60,
    )

    assert result.status == "matched"
    assert result.match is not None
    assert result.match.tmdb_id == 10
    assert result.match.release_date == date(2020, 9, 10)


def test_tmdb_client_rejects_ambiguous_matches(monkeypatch):
    from backend.integrations.tmdb import TMDbClient

    client = TMDbClient(access_token="test-token")
    payloads = {
        "/search/movie": {
            "results": [
                {"id": 1, "title": "The Movie", "popularity": 10},
                {"id": 2, "title": "The Movie", "popularity": 9},
            ]
        },
        "/movie/1": {
            "id": 1,
            "title": "The Movie",
            "runtime": 100,
            "release_date": "2020-01-01",
        },
        "/movie/2": {
            "id": 2,
            "title": "The Movie",
            "runtime": 100,
            "release_date": "2021-01-01",
        },
    }
    monkeypatch.setattr(client, "_get_json", lambda path, params=None: payloads[path])

    result = client.lookup_movie(title="The Movie", duration_seconds=100 * 60)

    assert result.status == "ambiguous"
    assert result.match is None
    assert "multiple similarly likely matches" in (result.detail or "")


def test_release_lookup_wrapper_uses_configured_read_token(monkeypatch):
    from backend.integrations import tmdb
    from backend.integrations.tmdb import TMDbLookupResult, TMDbMovieMatch
    from config.settings.settings import AppSettings

    settings = AppSettings(
        movie_metadata={
            "tmdb_read_access_token": "secret-token",
            "tmdb_api_base_url": "https://tmdb.example/3",
            "language": "en-US",
            "request_timeout_seconds": 4,
            "max_retries": 0,
        }
    )
    monkeypatch.setattr(tmdb, "get_settings", lambda: settings)
    seen = {}

    def fake_lookup(self, *, title, description=None, duration_seconds=0):
        seen["token"] = self._access_token
        seen["base_url"] = self._base_url
        seen["title"] = title
        return TMDbLookupResult(
            status="matched",
            match=TMDbMovieMatch(
                tmdb_id=123,
                title="A Movie",
                release_date=date(2020, 5, 4),
                confidence=0.99,
            ),
        )

    monkeypatch.setattr(tmdb.TMDbClient, "lookup_movie", fake_lookup)

    result = tmdb.lookup_movie_release_metadata(title="A Movie", duration_seconds=6000)

    assert result is not None
    assert result.status == "matched"
    assert result.release_date == date(2020, 5, 4)
    assert result.source == "tmdb"
    assert result.source_id == "123"
    assert seen == {
        "token": "secret-token",
        "base_url": "https://tmdb.example/3",
        "title": "A Movie",
    }


def test_movie_and_extra_downloads_share_one_persisted_release_lookup(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import (
        create_movie_download,
        create_movie_extra_download,
    )
    from backend.api.endpoints.movies import service as movie_service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, MovieLocalMediaProfile
    from backend.integrations.tmdb import MovieReleaseLookupResult
    from config import get_settings
    from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    lookup_calls = []

    def fake_lookup(*, title, description=None, duration_seconds=0):
        lookup_calls.append((title, duration_seconds))
        return MovieReleaseLookupResult(
            status="matched",
            attempted_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            release_date=date(2020, 9, 10),
            source="tmdb",
            source_id="718444",
        )

    monkeypatch.setattr(movie_service, "lookup_movie_release_metadata", fake_lookup)

    profile = MovieLocalMediaProfile(
        slug="plex-movies",
        name="Plex movies",
        output_template=(
            "/downloads/{{ movie_title }} ({{ year }})/{{ title }}"
            "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
        ),
        preferred_format="format_1080p",
        append_media_type_to_filename=False,
    )
    session.add(profile)
    session.commit()

    official_trailer = DwMovieExtraRecord(
        dw_id="trailer-1",
        slug="run-hide-fight-trailer",
        title="Official Trailer",
        movie_extra_type="trailer",
        sharing_url="https://www.dailywire.com/clips/run-hide-fight-trailer",
        duration=120,
    )
    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="run-hide-fight",
        title="Run Hide Fight",
        description="A student fights attackers at her high school.",
        duration=109 * 60,
        sharing_url="https://www.dailywire.com/videos/run-hide-fight",
        is_downloadable=True,
        movie_extras=[official_trailer],
        trailer=official_trailer,
    )
    body = MovieDownloadAPICreate(local_media_profile_id=profile.id)

    movie_download = create_movie_download(session, movie_data, body)
    trailer_download = create_movie_extra_download(
        session,
        movie_data,
        "run-hide-fight-trailer",
        body,
    )
    session.commit()

    movie = session.query(Movie).one()
    assert lookup_calls == [("Run Hide Fight", 109 * 60)]
    assert movie.release_date == date(2020, 9, 10)
    assert movie.release_date_source == "tmdb"
    assert movie.release_date_source_id == "718444"
    assert movie.release_date_lookup_status == "matched"
    assert movie.release_date_lookup_attempted_at is not None
    assert movie.release_date_lookup_error is None
    assert movie_download.file_path == str(
        tmp_path / "Run Hide Fight (2020)" / "Run Hide Fight.ext"
    )
    assert trailer_download.file_path == str(
        tmp_path / "Run Hide Fight (2020)" / "Official Trailer-trailer.ext"
    )

    session.close()
    engine.dispose()


def test_movie_release_date_condition_omits_unknown_metadata(tmp_path, monkeypatch):
    from backend.db.models import Movie
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_movie_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="a-movie",
        title="A Movie",
        description=None,
        downloaded_date=None,
        duration=100,
        release_date_lookup_status="ambiguous",
        release_date_lookup_error="TMDB returned two equally likely matches",
    )

    result = resolve_movie_output_path(
        "/downloads/{{ movie_title }}{% if year %} ({{ year }}){% endif %}/{{ movie }}.ext",
        movie=movie,
    )

    assert result == (tmp_path / "A Movie" / "a-movie.ext").resolve()


def test_show_date_component_placeholders_use_episode_publish_datetime(tmp_path, monkeypatch):
    from backend.utils.output_template import resolve_episode_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    episode = SimpleNamespace(
        show=SimpleNamespace(slug="show", title="Show"),
        season=SimpleNamespace(slug="season", name="Season"),
        slug="episode",
        title="Episode",
        episode_identifier="ep.1",
        published_date=datetime(2026, 8, 30, 12, 34, 56),
    )

    result = resolve_episode_output_path(
        "/downloads/{year}-{month}-{day}_{hour}-{minute}-{second}/{episode}.ext",
        episode=episode,
        extension="mp4",
    )

    assert result == (
        tmp_path / "2026-08-30_12-34-56" / "episode.mp4"
    ).resolve()
