from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _movie_page_payload(*, status: str = "scheduled", has_video: bool = False) -> dict:
    return {
        "hasVideo": has_video,
        "isDownloadable": has_video,
        "images": {
            "movie_app_background_image": "app.png",
            "movie_logo_image": "logo.png",
            "movie_ott_background_image": "ott.png",
            "movie_poster_image": "poster.png",
            "movie_thumbnail_image": "thumb.png",
            "movie_web_background_image": "web.png",
        },
        "runtime": 6540 if has_video else None,
        "pid": "movie-1",
        "background": "Movie background copy",
        "byline": "A Daily Wire Original Film",
        "description": "Movie description without a release-date parsing contract.",
        "language": "English",
        "originCountry": "United States",
        "publishedAt": "2026-09-16T05:08:00.000Z",
        "rating": "TV-14",
        "sharingURL": "https://www.dailywire.com/videos/upcoming-movie",
        "slug": "upcoming-movie",
        "status": status,
        "title": "Upcoming Movie | Final Trailer",
        "availableFor": ["INSIDER", "ALL_ACCESS"],
        "castAndCrew": [{
            "name": "Director Person",
            "imageSize": "cast_and_crew_image_1x1",
            "imageUrl": "director.png",
            "info": "Writer/Director",
            "roleText": "Director",
        }],
        "directedBy": ["Director Person"],
        "extras": [{
            "duration": 66.859422,
            "images": {"extra_thumbnail_image": "trailer.png"},
            "pid": "trailer-1",
            "description": "Trailer description",
            "publishedAt": "2026-09-04T09:30:00.000Z",
            "sharingURL": "https://www.dailywire.com/clips/upcoming-movie-final-trailer",
            "slug": "upcoming-movie-final-trailer",
            "title": "Upcoming Movie | Final Trailer",
            "availableFor": ["FREE", "ANONYMOUS"],
        }],
        "genres": [],
        "hosts": [{
            "images": {
                "host_image_1x1": "host.png",
                "host_logo_image": "host-logo.png",
            },
            "pid": "host-1",
            "name": "DailyWire+",
            "slug": "dailywire-plus",
        }],
        "moreLikeThis": [{
            "images": {"movie_poster_image": "related.png"},
            "contentType": "movie",
            "publishedAt": "2021-01-14T22:10:51.000Z",
            "slug": "related-movie",
            "title": "Related Movie",
        }],
        "productionCompanies": [],
        "shopItems": [],
        "starring": ["Lead Actor"],
        "writtenBy": ["Director Person"],
        "trailer": {
            "continueWatchingEntityId": "trailer-1",
            "continueWatchingEntityType": "CLIP",
            "duration": 66.859422,
            "images": {"extra_thumbnail_image": "trailer.png"},
            "pid": "trailer-1",
            "description": "Trailer description",
            "sharingURL": "https://www.dailywire.com/clips/upcoming-movie-final-trailer",
            "slug": "upcoming-movie-final-trailer",
            "title": "Upcoming Movie | Final Trailer",
            "muxDrmToken": "",
            "muxPlaybackId": "playback-id",
            "muxPlaybackToken": "signed-token",
            "playbackPolicy": "signed",
            "publishedAt": "2026-09-04T09:30:00.000Z",
            "trailerURL": "https://stream.mux.com/playback-id.m3u8?token=signed-token",
        },
    }


def test_movie_page_uses_structured_status_and_release_instant(monkeypatch):
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    calls = []
    client = MovieMiddlewareClient(base_url="https://example.invalid")

    def fake_get(endpoint, params):
        calls.append((endpoint, params))
        return _movie_page_payload()

    monkeypatch.setattr(client, "_get", fake_get)
    movie = client.get_movie_page("upcoming-movie")

    assert calls == [("v4/getMoviePage", {"slug": "upcoming-movie"})]
    assert movie.dw_id == "movie-1"
    assert movie.title == "Upcoming Movie"
    assert movie.extended_title == "Upcoming Movie | Final Trailer"
    assert movie.status == "scheduled"
    assert movie.is_upcoming is True
    assert movie.expected_release_date == date(2026, 9, 16)
    assert movie.published_at == datetime(2026, 9, 16, 5, 8, tzinfo=timezone.utc)
    assert movie.duration == 0
    assert movie.has_video is False
    assert movie.mature_rating == "TV-14"
    assert movie.author_name == "DailyWire+"
    assert movie.cast_and_crew[0].role_text == "Director"
    assert movie.more_like_this[0].slug == "related-movie"
    assert movie.movie_extras[0].dw_id == "trailer-1"
    assert movie.movie_extras[0].available_for == ["FREE", "ANONYMOUS"]
    assert movie.movie_extras[0].thumbnail_landscape_path == "trailer.png"
    assert movie.trailer is not None
    assert movie.trailer.mux_playback_id == "playback-id"
    assert movie.trailer.trailer_url is not None


def test_published_status_is_not_upcoming(monkeypatch):
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    client = MovieMiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(
        client,
        "_get",
        lambda endpoint, params: _movie_page_payload(status="published", has_video=True),
    )

    movie = client.get_movie_page("upcoming-movie")

    assert movie.status == "published"
    assert movie.is_upcoming is False
    assert movie.expected_release_date is None
    assert movie.has_video is True
    assert movie.is_downloadable is True
    assert movie.duration == 6540


def test_catalog_movie_fallback_never_advertises_full_movie_download(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service
    from dailywire_api.records import DwCatalogMovieRecord, DwCatalogRecord

    monkeypatch.setattr(
        service,
        "get_catalog",
        lambda: DwCatalogRecord(movies=[
            DwCatalogMovieRecord(
                dw_id="movie-1",
                slug="upcoming-movie",
                title="Upcoming Movie",
                description="Catalog description",
            )
        ]),
    )

    movie = service._catalog_movie_fallback("upcoming-movie")

    assert movie is not None
    assert movie.is_downloadable is False
    assert movie.has_video is False
    assert movie.status == "unknown"


def test_sync_dailywire_movie_metadata_persists_rich_movie_page(monkeypatch):
    from backend.api.endpoints.movies.service import index_dailywire_movie
    from backend.db.core import Base
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    client = MovieMiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "_get", lambda endpoint, params: _movie_page_payload())
    record = client.get_movie_page("upcoming-movie")

    movie, created = index_dailywire_movie(session, record)
    session.commit()
    session.refresh(movie)

    assert created is True
    assert movie.status == "scheduled"
    assert movie.has_video is False
    assert movie.published_at == datetime(2026, 9, 16, 5, 8, tzinfo=timezone.utc)
    assert movie.release_date == date(2026, 9, 16)
    assert movie.release_date_source == "dailywire"
    assert movie.release_date_source_id == "movie-1"
    assert movie.release_date_lookup_status == "matched"
    assert movie.background == "Movie background copy"
    assert movie.byline == "A Daily Wire Original Film"
    assert movie.language == "English"
    assert movie.origin_country == "United States"
    assert movie.images["movie_web_background_image"] == "web.png"
    assert movie.cast_and_crew[0]["role_text"] == "Director"
    assert movie.directed_by == ["Director Person"]
    assert movie.hosts[0]["slug"] == "dailywire-plus"
    assert movie.more_like_this[0]["slug"] == "related-movie"
    assert movie.starring == ["Lead Actor"]
    assert movie.written_by == ["Director Person"]
    assert movie.movie_extras[0].available_for == ["FREE", "ANONYMOUS"]

    session.close()
    engine.dispose()
