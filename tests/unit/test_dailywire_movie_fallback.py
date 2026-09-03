from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest


def _movie_record():
    from dailywire_api.records import DwMovieRecord

    return DwMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        duration=5400,
        sharing_url="https://www.dailywire.com/videos/a-movie",
    )


def _install_failing_client(monkeypatch, service):
    from dailywire_api.dw_api.client import MiddlewareAPIError

    class FakeAuthClient:
        @staticmethod
        def get_token():
            return None

    class FakeMiddlewareClient:
        def __init__(self, **kwargs):
            assert kwargs["access_token"] is None
            assert kwargs["pace_requests"] is False

        @staticmethod
        def get_movie_page(slug):
            assert slug == "a-movie"
            raise MiddlewareAPIError("HTTP error 502: upstream unavailable", status_code=502)

    monkeypatch.setattr(service, "DeviceAuthClient", FakeAuthClient)
    monkeypatch.setattr(service, "MiddlewareClient", FakeMiddlewareClient)


def test_movie_detail_uses_indexed_movie_without_calling_dailywire(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service

    indexed = _movie_record()
    monkeypatch.setattr(service, "_indexed_movie_fallback", lambda slug: indexed)

    class DailyWireMustNotBeCalled:
        def __init__(self, **_kwargs):
            raise AssertionError("indexed movie pages must not call Daily Wire")

    def catalog_must_not_be_used(_slug):
        raise AssertionError("catalog fallback should not run for an indexed movie")

    monkeypatch.setattr(service, "MiddlewareClient", DailyWireMustNotBeCalled)
    monkeypatch.setattr(service, "_catalog_movie_fallback", catalog_must_not_be_used)

    assert service.get_movie("a-movie") == indexed


def test_movie_detail_uses_live_dailywire_data_when_not_indexed(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service

    live_movie = _movie_record()
    monkeypatch.setattr(service, "_indexed_movie_fallback", lambda slug: None)

    class FakeAuthClient:
        @staticmethod
        def get_token():
            return SimpleNamespace(access_token="token")

    class FakeMiddlewareClient:
        def __init__(self, **kwargs):
            assert kwargs == {"access_token": "token", "pace_requests": False}

        @staticmethod
        def get_movie_page(slug):
            assert slug == "a-movie"
            return live_movie

    def catalog_must_not_be_used(_slug):
        raise AssertionError("catalog fallback should only run after a live detail failure")

    monkeypatch.setattr(service, "DeviceAuthClient", FakeAuthClient)
    monkeypatch.setattr(service, "MiddlewareClient", FakeMiddlewareClient)
    monkeypatch.setattr(service, "_catalog_movie_fallback", catalog_must_not_be_used)

    assert service.get_movie("a-movie") == live_movie


def test_movie_detail_uses_catalog_fallback_when_not_indexed(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service

    _install_failing_client(monkeypatch, service)
    catalog_movie = _movie_record()
    monkeypatch.setattr(service, "_indexed_movie_fallback", lambda slug: None)
    monkeypatch.setattr(service, "_catalog_movie_fallback", lambda slug: catalog_movie)

    assert service.get_movie("a-movie") == catalog_movie


def test_movie_detail_preserves_upstream_error_without_a_fallback(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service
    from dailywire_api.dw_api.client import MiddlewareAPIError

    _install_failing_client(monkeypatch, service)
    monkeypatch.setattr(service, "_indexed_movie_fallback", lambda slug: None)
    monkeypatch.setattr(service, "_catalog_movie_fallback", lambda slug: None)

    with pytest.raises(MiddlewareAPIError, match="HTTP error 502"):
        service.get_movie("a-movie")


def test_indexed_movie_fallback_preserves_extras_and_official_trailer(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service

    published = datetime(2026, 8, 30, 12, 34, 56)
    trailer = SimpleNamespace(
        id=11,
        dw_id="trailer-1",
        slug="a-movie-trailer",
        title="A Movie | Official Trailer",
        movie_extra_type="trailer",
        description="Trailer",
        sharing_url="https://www.dailywire.com/clips/a-movie-trailer",
        published_date=published,
        duration=90,
        background_image_path=None,
        thumbnail_landscape_path="trailer.jpg",
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
    )
    movie = SimpleNamespace(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        extended_title="A Movie | Original",
        description="Movie description",
        author_name="Host",
        author_slug="host",
        background_image_path="background.jpg",
        logo_image_path="logo.png",
        thumbnail_landscape_path="land.jpg",
        thumbnail_portrait_path="port.jpg",
        thumbnail_square_path="square.jpg",
        duration=5400,
        sharing_url="https://www.dailywire.com/videos/a-movie",
        mature_rating="PG-13",
        is_downloadable=True,
        available_for=["ALL_ACCESS"],
        movie_extras=[trailer],
        official_trailer_id=11,
    )

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        @staticmethod
        def one_or_none():
            return movie

    class FakeSession:
        @staticmethod
        def query(_model):
            return FakeQuery()

    @contextmanager
    def fake_db_session():
        yield FakeSession()

    monkeypatch.setattr(service, "db_session", fake_db_session)

    result = service._indexed_movie_fallback("a-movie")

    assert result is not None
    assert result.duration == 5400
    assert result.trailer is not None
    assert result.trailer.slug == "a-movie-trailer"
    assert result.movie_extras == [result.trailer]
    assert result.trailer.published_date is not None
    assert result.trailer.published_date.tzinfo is not None


def test_catalog_movie_fallback_builds_renderable_detail_record(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service
    from dailywire_api.records import DwCatalogMovieRecord, DwCatalogRecord

    summary = DwCatalogMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        description="Movie description",
        thumbnail_landscape_path="land.jpg",
    )
    monkeypatch.setattr(
        service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[summary]),
    )

    result = service._catalog_movie_fallback("a-movie")

    assert result is not None
    assert result.title == "A Movie"
    assert result.description == "Movie description"
    assert result.sharing_url == "https://www.dailywire.com/videos/a-movie"
    assert result.duration == 0
    assert result.movie_extras == []
