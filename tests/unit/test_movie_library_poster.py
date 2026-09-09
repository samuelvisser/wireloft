from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _movie_page_record(*, poster: str):
    from dailywire_api.records import DwMovieRecord

    return DwMovieRecord(
        dw_id="movie-1",
        slug="run-hide-fight-infidels",
        title="Run Hide Fight: Infidels",
        extended_title="Run Hide Fight: Infidels",
        sharing_url="https://www.dailywire.com/videos/run-hide-fight-infidels",
        status="scheduled",
        published_at=datetime(2026, 9, 16, 5, 8, tzinfo=timezone.utc),
        thumbnail_portrait_path=poster,
    )


def _catalog_record(*, poster: str, extended_title: str = "Run Hide Fight: Infidels"):
    from dailywire_api.records import DwCatalogMovieRecord

    return DwCatalogMovieRecord(
        dw_id="catalog-movie-1",
        slug="run-hide-fight-infidels",
        title="Run Hide Fight: Infidels",
        extended_title=extended_title,
        thumbnail_portrait_path=poster,
    )


def test_reliable_catalog_poster_is_persisted_when_movie_is_indexed(monkeypatch) -> None:
    from backend.api.endpoints.dailywire.movies import service as dailywire_movie_service
    from backend.api.endpoints.movies.service import index_dailywire_movie
    from backend.db.core import Base
    from dailywire_api.records import DwCatalogRecord

    live_movie = _movie_page_record(poster="wrong-movie-page-poster.png")
    catalog_movie = _catalog_record(poster="correct-catalog-poster.png")

    class FakeMovieClient:
        def __init__(self, **kwargs):
            assert kwargs == {"access_token": None, "pace_requests": False}

        def get_movie_page(self, slug: str):
            assert slug == "run-hide-fight-infidels"
            return live_movie

    monkeypatch.setattr(
        dailywire_movie_service,
        "DeviceAuthClient",
        lambda: SimpleNamespace(get_token=lambda: None),
    )
    monkeypatch.setattr(dailywire_movie_service, "MovieMiddlewareClient", FakeMovieClient)
    monkeypatch.setattr(
        dailywire_movie_service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[catalog_movie]),
    )

    resolved = dailywire_movie_service.get_live_movie("run-hide-fight-infidels")
    assert resolved.thumbnail_portrait_path == "correct-catalog-poster.png"

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        movie, created = index_dailywire_movie(session, resolved)
        session.commit()
        session.refresh(movie)

        assert created is True
        assert movie.thumbnail_portrait_path == "correct-catalog-poster.png"
    finally:
        session.close()
        engine.dispose()


def test_promotional_catalog_art_does_not_replace_canonical_movie_poster(monkeypatch) -> None:
    from backend.api.endpoints.dailywire.movies import service as dailywire_movie_service
    from dailywire_api.records import DwCatalogRecord

    live_movie = _movie_page_record(poster="canonical-movie-poster.png")
    catalog_movie = _catalog_record(
        poster="trailer-promo-poster.png",
        extended_title="Run Hide Fight: Infidels | Final Trailer",
    )

    class FakeMovieClient:
        def __init__(self, **_kwargs):
            pass

        def get_movie_page(self, slug: str):
            assert slug == "run-hide-fight-infidels"
            return live_movie

    monkeypatch.setattr(
        dailywire_movie_service,
        "DeviceAuthClient",
        lambda: SimpleNamespace(get_token=lambda: None),
    )
    monkeypatch.setattr(dailywire_movie_service, "MovieMiddlewareClient", FakeMovieClient)
    monkeypatch.setattr(
        dailywire_movie_service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[catalog_movie]),
    )

    resolved = dailywire_movie_service.get_live_movie("run-hide-fight-infidels")

    assert resolved.thumbnail_portrait_path == "canonical-movie-poster.png"
