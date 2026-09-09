from __future__ import annotations

from types import SimpleNamespace


def test_movie_page_images_map_to_wireloft_poster_fields() -> None:
    from dailywire_api.records import DwMovieRecord

    movie = DwMovieRecord.model_validate({
        "pid": "movie-1",
        "slug": "upcoming-movie",
        "title": "Upcoming Movie | Final Trailer",
        "sharingURL": "https://www.dailywire.com/videos/upcoming-movie",
        "status": "scheduled",
        "images": {
            "movie_poster_image": "canonical-poster.png",
            "movie_thumbnail_image": "canonical-thumbnail.png",
            "movie_web_background_image": "canonical-background.png",
        },
    })

    assert movie.title == "Upcoming Movie"
    assert movie.thumbnail_portrait_path == "canonical-poster.png"
    assert movie.thumbnail_landscape_path == "canonical-thumbnail.png"
    assert movie.background_image_path == "canonical-background.png"


def test_catalog_promotional_movie_uses_canonical_movie_page_art(monkeypatch) -> None:
    from backend.api.endpoints.dailywire.catalog import service
    from dailywire_api.records import DwCatalogMovieRecord, DwCatalogRecord, DwMovieRecord

    browse_movie = DwCatalogMovieRecord(
        dw_id="promotional-video-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        extended_title="Upcoming Movie | Final Trailer",
        thumbnail_portrait_path="trailer-promo.png",
        thumbnail_landscape_path="trailer-landscape.png",
        background_image_path="trailer-background.png",
    )
    canonical_movie = DwMovieRecord(
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        extended_title="Upcoming Movie | Final Trailer",
        sharing_url="https://www.dailywire.com/videos/upcoming-movie",
        status="scheduled",
        thumbnail_portrait_path="canonical-poster.png",
        thumbnail_landscape_path="canonical-thumbnail.png",
        background_image_path="canonical-background.png",
    )

    calls: list[str] = []

    class FakeMovieClient:
        def __init__(self, **kwargs):
            assert kwargs == {"access_token": "token", "pace_requests": False}

        def get_movie_page(self, slug: str):
            calls.append(slug)
            return canonical_movie

    monkeypatch.setattr(
        service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[browse_movie]),
    )
    monkeypatch.setattr(
        service,
        "DeviceAuthClient",
        lambda: SimpleNamespace(get_token=lambda: SimpleNamespace(access_token="token")),
    )
    monkeypatch.setattr(service, "MovieMiddlewareClient", FakeMovieClient)

    page = service.get_catalog_movies(offset=0, limit=24, search=None)

    assert calls == ["upcoming-movie"]
    assert len(page.items) == 1
    movie = page.items[0]
    assert movie.dw_id == "promotional-video-1"
    assert movie.title == "Upcoming Movie"
    assert movie.extended_title == "Upcoming Movie | Final Trailer"
    assert movie.thumbnail_portrait_path == "canonical-poster.png"
    assert movie.thumbnail_landscape_path == "canonical-thumbnail.png"
    assert movie.background_image_path == "canonical-background.png"


def test_catalog_missing_portrait_also_uses_canonical_movie_page_art(monkeypatch) -> None:
    from backend.api.endpoints.dailywire.catalog import service
    from dailywire_api.records import DwCatalogMovieRecord, DwCatalogRecord, DwMovieRecord

    browse_movie = DwCatalogMovieRecord(
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        extended_title="Upcoming Movie",
        thumbnail_portrait_path=None,
        thumbnail_landscape_path="trailer-landscape.png",
    )
    canonical_movie = DwMovieRecord(
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        sharing_url="https://www.dailywire.com/videos/upcoming-movie",
        status="scheduled",
        thumbnail_portrait_path="canonical-poster.png",
        thumbnail_landscape_path="canonical-thumbnail.png",
    )

    class FakeMovieClient:
        def __init__(self, **_kwargs):
            pass

        def get_movie_page(self, slug: str):
            assert slug == "upcoming-movie"
            return canonical_movie

    monkeypatch.setattr(
        service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[browse_movie]),
    )
    monkeypatch.setattr(
        service,
        "DeviceAuthClient",
        lambda: SimpleNamespace(get_token=lambda: None),
    )
    monkeypatch.setattr(service, "MovieMiddlewareClient", FakeMovieClient)

    page = service.get_catalog_movies(offset=0, limit=24, search=None)

    assert page.items[0].thumbnail_portrait_path == "canonical-poster.png"


def test_indexed_movie_persists_canonical_movie_page_art(monkeypatch) -> None:
    import backend.db.models  # noqa: F401
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.api.endpoints.movies import service
    from backend.db import Base
    from backend.db.models import Movie
    from dailywire_api.records import DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        monkeypatch.setattr(service, "ensure_movie_release_metadata", lambda *_args: None)
        movie_data = DwMovieRecord.model_validate({
            "pid": "movie-1",
            "slug": "upcoming-movie",
            "title": "Upcoming Movie | Final Trailer",
            "sharingURL": "https://www.dailywire.com/videos/upcoming-movie",
            "status": "scheduled",
            "images": {
                "movie_poster_image": "canonical-poster.png",
                "movie_thumbnail_image": "canonical-thumbnail.png",
                "movie_web_background_image": "canonical-background.png",
            },
        })

        movie, created = service.index_dailywire_movie(session, movie_data)
        session.commit()
        session.expire_all()

        persisted = session.query(Movie).filter(Movie.id == movie.id).one()
        assert created is True
        assert persisted.thumbnail_portrait_path == "canonical-poster.png"
        assert persisted.thumbnail_landscape_path == "canonical-thumbnail.png"
        assert persisted.background_image_path == "canonical-background.png"
    finally:
        session.close()
        engine.dispose()
