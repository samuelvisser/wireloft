from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _upcoming_movie_payload() -> dict:
    return {
        "video": {
            "id": "b96f10fd-b2bc-4389-88d0-e4feefa62a8b",
            "slug": "run-hide-fight-infidels",
            "title": "Run Hide Fight: Infidels | Final Trailer",
            "description": (
                "Final Trailer | When radical Islamic terrorists hijack a liberal college's "
                "pro-Palestine encampment. Coming exclusively to The Daily Wire, September 16."
            ),
            "duration": 0,
            "sharingURL": "https://www.dailywire.com/videos/run-hide-fight-infidels",
            "isDownloadable": False,
            "availableFor": ["READER", "INSIDER", "INSIDER_PLUS", "ALL_ACCESS"],
        },
        "tabs": [
            {
                "title": "Extras",
                "components": [
                    {
                        "items": [
                            {
                                "showEpisode": {
                                    "id": "eb5b1a5f-771f-4c99-922a-55bdcb938193",
                                    "slug": "run-hide-fight-infidels-final-trailer",
                                    "title": "Run Hide Fight: Infidels | Final Trailer",
                                    "duration": 66.859422,
                                    # Daily Wire currently returns these timestamps
                                    # without a UTC suffix on this upcoming movie.
                                    "publishedAt": "2026-09-03T20:59:43.974",
                                    "sharingURL": (
                                        "https://www.dailywire.com/clips/"
                                        "run-hide-fight-infidels-final-trailer"
                                    ),
                                }
                            },
                            {
                                "showEpisode": {
                                    "id": "f7dd2942-67bb-406d-bcd1-774ca731246c",
                                    "slug": "run-hide-fight-infidels-official-trailer",
                                    "title": "Run Hide Fight: Infidels | Official Trailer",
                                    "duration": 128.546044,
                                    "publishedAt": "2026-08-20T15:42:20.173",
                                    "sharingURL": (
                                        "https://www.dailywire.com/clips/"
                                        "run-hide-fight-infidels-official-trailer"
                                    ),
                                }
                            },
                        ]
                    }
                ],
            }
        ],
    }


def test_upcoming_movie_accepts_naive_extra_dates_and_exposes_release_metadata(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    client = MiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "_get", lambda endpoint, params: _upcoming_movie_payload())

    movie = client.get_movie_page("run-hide-fight-infidels")

    assert movie.title == "Run Hide Fight: Infidels"
    assert movie.is_downloadable is False
    assert movie.is_upcoming is True
    assert movie.expected_release_date == date(2026, 9, 16)
    assert len(movie.movie_extras) == 2
    assert movie.trailer is not None
    assert movie.trailer.movie_extra_type == "trailer"
    assert movie.movie_extras[0].published_date == datetime(
        2026,
        9,
        3,
        20,
        59,
        43,
        974000,
        tzinfo=timezone.utc,
    )


def test_catalog_movie_fallback_never_advertises_full_movie_download(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service
    from dailywire_api.records import DwCatalogMovieRecord, DwCatalogRecord

    monkeypatch.setattr(
        service,
        "get_catalog",
        lambda: DwCatalogRecord(
            movies=[
                DwCatalogMovieRecord(
                    dw_id="movie-1",
                    slug="upcoming-movie",
                    title="Upcoming Movie",
                    description="Coming exclusively to The Daily Wire, September 16.",
                )
            ]
        ),
    )

    movie = service._catalog_movie_fallback("upcoming-movie")

    assert movie is not None
    assert movie.is_downloadable is False


def test_sync_dailywire_movie_metadata_captures_upcoming_release_transition():
    from backend.api.endpoints.movies.service import sync_dailywire_movie_metadata
    from backend.db.core import Base
    from backend.db.models import Movie
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    movie = Movie(
        uuid="movie-upcoming-uuid",
        type=MediaType.MOVIE.value,
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        description="Coming soon",
        downloaded_date=None,
        duration=0,
        is_downloadable=False,
        available_for=[],
    )
    session.add(movie)
    session.commit()

    released = DwMovieRecord(
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie",
        description="Now available",
        duration=7200,
        sharing_url="https://www.dailywire.com/videos/upcoming-movie",
        is_downloadable=True,
        available_for=["ALL_ACCESS"],
    )

    sync_dailywire_movie_metadata(session, movie=movie, movie_data=released)
    session.commit()
    session.refresh(movie)

    assert movie.is_downloadable is True
    assert movie.duration == 7200
    assert movie.description == "Now available"
    assert movie.available_for == ["ALL_ACCESS"]

    session.close()
    engine.dispose()
