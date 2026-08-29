from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _catalog_payload():
    return {
        "components": [
            {
                "items": [
                    {
                        "type": "Show",
                        "show": {
                            "id": "show-2",
                            "slug": "z-show",
                            "title": "Z Show",
                            "host": {"slug": "host-b", "name": "Host B"},
                            "images": {"thumbnail": {"port": "z.jpg"}},
                        },
                    },
                    {
                        "type": "Video",
                        "video": {
                            "id": "movie-1",
                            "slug": "a-movie",
                            "title": "A Movie",
                            "host": {"slug": "host-a", "name": "Host A"},
                            "images": {"thumbnail": {"port": "movie.jpg"}},
                        },
                    },
                ]
            },
            {
                "items": [
                    {
                        "type": "Show",
                        "show": {
                            "id": "show-1",
                            "slug": "a-show",
                            "title": "A Show",
                            "host": {"slug": "host-a", "name": "Host A"},
                        },
                    },
                    {
                        "type": "Show",
                        "show": {"id": "show-2", "slug": "z-show", "title": "Z Show"},
                    },
                ]
            },
        ]
    }


def test_dailywire_catalog_flattens_sorts_and_deduplicates(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    client = MiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "_get", lambda endpoint, params: _catalog_payload())

    catalog = client.get_catalog()

    assert [show.slug for show in catalog.shows] == ["a-show", "z-show"]
    assert [movie.slug for movie in catalog.movies] == ["a-movie"]
    assert catalog.shows[1].author_name == "Host B"


def test_dailywire_catalog_uses_short_movie_display_titles(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    payload = {
        "components": [{
            "items": [
                {"video": {
                    "id": "movie-1",
                    "slug": "bonhoeffer",
                    "title": "Bonhoeffer: Pastor. Spy. Assassin. A long marketing description.",
                    "description": "A long marketing description.",
                }},
                {"video": {
                    "id": "movie-2",
                    "slug": "run-hide-fight",
                    "title": "Run Hide Fight | Watch The First One | More marketing copy",
                    "description": "More marketing copy",
                }},
            ],
        }],
    }
    client = MiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "_get", lambda endpoint, params: payload)

    catalog = client.get_catalog()

    assert [movie.title for movie in catalog.movies] == [
        "Bonhoeffer: Pastor. Spy. Assassin.",
        "Run Hide Fight",
    ]
    assert [movie.extended_title for movie in catalog.movies] == [
        "Bonhoeffer: Pastor. Spy. Assassin. A long marketing description.",
        "Run Hide Fight | Watch The First One | More marketing copy",
    ]


def test_dailywire_catalog_pages_filter_sort_and_preserve_offsets(monkeypatch):
    from backend.api.endpoints.dailywire.catalog import service
    from dailywire_api.records import DwCatalogRecord, DwCatalogShowRecord

    catalog = DwCatalogRecord(shows=[
        DwCatalogShowRecord(dw_id="3", slug="z", title="Zulu", author_name="Host B"),
        DwCatalogShowRecord(dw_id="1", slug="b", title="Beta", author_name="Host A"),
        DwCatalogShowRecord(dw_id="2", slug="a", title="Alpha", author_name="Host A"),
    ])
    monkeypatch.setattr(service, "get_catalog", lambda: catalog)

    first_page = service.get_catalog_shows(
        offset=0, limit=2, search=None, grouping="host",
    )
    second_page = service.get_catalog_shows(
        offset=2, limit=2, search=None, grouping="host",
    )
    filtered = service.get_catalog_shows(
        offset=0, limit=2, search="zulu host", grouping="alphabetical",
    )

    assert [show.slug for show in first_page.items] == ["a", "b"]
    assert first_page.has_more is True
    assert [show.slug for show in second_page.items] == ["z"]
    assert second_page.has_more is False
    assert filtered.total == 1
    assert [show.slug for show in filtered.items] == ["z"]


def test_dailywire_movie_page_exposes_trailer(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    payload = {
        "video": {
            "id": "movie-1",
            "slug": "a-movie",
            "title": "A Movie",
            "description": "Movie description",
            "duration": 5400,
            "sharingURL": "https://www.dailywire.com/videos/a-movie",
            "isDownloadable": True,
            "availableFor": ["ALL_ACCESS"],
            "images": {"thumbnail": {"land": "land.jpg", "port": "port.jpg"}},
        },
        "tabs": [
            {
                "components": [
                    {
                        "items": [
                            {
                                "showEpisode": {
                                    "id": "trailer-1",
                                    "slug": "a-movie-trailer",
                                    "title": "A Movie | Official Trailer",
                                    "sharingURL": "https://www.dailywire.com/clips/a-movie-trailer",
                                    "duration": 90,
                                    "images": {"thumbnail": {"land": "trailer.jpg"}},
                                }
                            }
                        ]
                    }
                ]
            }
        ],
    }
    client = MiddlewareClient(base_url="https://example.invalid")
    monkeypatch.setattr(client, "_get", lambda endpoint, params: payload)

    movie = client.get_movie_page("a-movie")

    assert movie.duration == 5400
    assert movie.trailer is not None
    assert movie.trailer.slug == "a-movie-trailer"


def test_dailywire_movie_playback_resolves_secure_url_with_api_authorization(monkeypatch):
    from dailywire_api.dw_api import client as client_module
    from dailywire_api.dw_api.client import MiddlewareClient

    secure_url = "https://middleware.example/middleware/v2/getSecureVideoURL?d=opaque"
    playback_url = "https://stream.example/movie/master.m3u8?token=signed"
    client = MiddlewareClient(
        access_token="account-token",
        base_url="https://middleware.example/middleware",
    )
    monkeypatch.setattr(client, "_get", lambda endpoint, params: {
        "video": {
            "hasVideo": True,
            "secureVideoURL": secure_url,
            "videoURL": "https://stream.example/trailer.m3u8",
            "trailerURL": "https://stream.example/trailer.m3u8",
        }
    })

    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            return None

        @staticmethod
        def read():
            return ('{"destination": "' + playback_url + '"}').encode()

    def fake_urlopen(request, *, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_module, "_wait_before_request", lambda: None)

    playback = client.get_movie_playback("a-movie")

    assert playback.video_url == playback_url
    assert playback.trailer_url == "https://stream.example/trailer.m3u8"
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == secure_url
    assert request.get_header("Authorization") == "Bearer account-token"
    assert timeout == 30.0


def test_dailywire_movie_playback_does_not_send_token_to_direct_media_url(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    direct_url = "https://stream.example/movie/master.m3u8?token=signed"
    client = MiddlewareClient(
        access_token="account-token",
        base_url="https://middleware.example/middleware",
    )
    monkeypatch.setattr(client, "_get", lambda endpoint, params: {
        "video": {
            "hasVideo": True,
            "secureVideoURL": direct_url,
        }
    })
    resolver_calls = []
    monkeypatch.setattr(client, "_get_url", lambda url: resolver_calls.append(url))

    playback = client.get_movie_playback("a-movie")

    assert playback.video_url == direct_url
    assert resolver_calls == []


def test_create_movie_download_persists_movie_and_uses_local_profile(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import create_movie_download, get_media_downloads_view
    from backend.api.endpoints.movies import service as movie_service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, MovieLocalMediaProfile, Trailer
    from backend.db.models.media_download import MovieMediaDownload
    from config import get_settings
    from dailywire_api.records import DwMovieRecord, DwTrailerRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    profile = MovieLocalMediaProfile(
        slug="movies",
        name="Movies",
        output_template="/downloads/{movie_title}/{movie}.ext",
        preferred_format="format_1080p",
    )
    session.add(profile)
    session.commit()

    create_movie_calls = []
    original_create_movie = movie_service.create_movie

    def tracked_create_movie(s, body):
        create_movie_calls.append(body)
        return original_create_movie(s, body)

    monkeypatch.setattr(movie_service, "create_movie", tracked_create_movie)

    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        extended_title="A Movie | A Daily Wire Original",
        description="Movie description",
        duration=5400,
        sharing_url="https://www.dailywire.com/videos/a-movie",
        author_name="A Director",
        author_slug="a-director",
        logo_image_path="movie-logo.png",
        mature_rating="PG-13",
        is_downloadable=True,
        available_for=["ALL_ACCESS"],
        trailer=DwTrailerRecord(
            dw_id="trailer-1",
            slug="a-movie-trailer",
            title="A Movie | Official Trailer",
            sharing_url="https://www.dailywire.com/clips/a-movie-trailer",
            duration=90,
        ),
    )

    download = create_movie_download(
        session,
        movie_data,
        MovieDownloadAPICreate(local_media_profile_id=profile.id),
    )
    session.commit()

    movie = session.query(Movie).one()
    trailer = session.query(Trailer).one()
    assert len(create_movie_calls) == 1
    assert create_movie_calls[0].author_slug == "a-director"
    assert create_movie_calls[0].logo_image_path == "movie-logo.png"
    assert create_movie_calls[0].available_for == ["ALL_ACCESS"]
    assert movie.slug == "a-movie"
    assert movie.extended_title == "A Movie | A Daily Wire Original"
    assert movie.author_slug == "a-director"
    assert movie.logo_image_path == "movie-logo.png"
    assert movie.available_for == ["ALL_ACCESS"]
    assert movie.trailers == [trailer]
    assert trailer.type == "trailer"
    assert trailer.movie_id == movie.id
    assert trailer.dw_id == "trailer-1"
    assert trailer.slug == "a-movie-trailer"
    assert trailer.duration == 90
    assert isinstance(download, MovieMediaDownload)
    assert download.type == "movie"
    assert download.file_path == str(tmp_path / "A Movie" / "a-movie.ext")
    view = get_media_downloads_view(session, movie_slug="a-movie")
    assert len(view) == 1
    assert view[0].movie_slug == "a-movie"
    assert view[0].movie_title == "A Movie"
    assert view[0].episode_slug is None

    session.close()
    engine.dispose()


def test_create_movie_supports_multiple_trailers_in_one_transaction():
    from backend.api.endpoints.movies.service import create_movie
    from backend.api.models.movie import MovieAPICreate
    from backend.api.models.trailer import TrailerAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, Trailer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    result = create_movie(session, MovieAPICreate(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        sharing_url="https://example.test/a-movie",
        trailers=[
            TrailerAPICreate(
                dw_id="trailer-1",
                slug="a-movie-trailer",
                title="Official Trailer",
                sharing_url="https://example.test/a-movie-trailer",
            ),
            TrailerAPICreate(
                dw_id="trailer-2",
                slug="a-movie-teaser",
                title="Teaser",
                sharing_url="https://example.test/a-movie-teaser",
            ),
        ],
    ))
    session.commit()

    movie = session.query(Movie).one()
    trailers = session.query(Trailer).order_by(Trailer.id).all()
    assert result.id == movie.id
    assert [trailer.slug for trailer in result.trailers] == [
        "a-movie-trailer",
        "a-movie-teaser",
    ]
    assert movie.trailers == trailers
    assert {trailer.movie_id for trailer in trailers} == {movie.id}

    session.close()
    engine.dispose()


def test_create_trailer_requires_an_existing_movie():
    from fastapi import HTTPException

    from backend.api.endpoints.trailers.service import create_trailer
    from backend.api.models.trailer import TrailerAPICreate
    from backend.db.core import Base
    from backend.db.models import Trailer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    with pytest.raises(HTTPException) as exc_info:
        create_trailer(session, 999, TrailerAPICreate(
            dw_id="trailer-1",
            slug="orphan-trailer",
            title="Orphan Trailer",
        ))

    assert exc_info.value.status_code == 404
    assert session.query(Trailer).count() == 0

    session.close()
    engine.dispose()


def test_movie_download_rolls_back_movie_and_trailer_together(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads import service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, MovieLocalMediaProfile, Trailer
    from backend.db.models.media_download import MovieMediaDownload
    from config import get_settings
    from dailywire_api.records import DwMovieRecord, DwTrailerRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    profile = MovieLocalMediaProfile(
        slug="movies",
        name="Movies",
        output_template="/downloads/{movie}.ext",
        preferred_format="format_1080p",
    )
    session.add(profile)
    session.commit()

    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        sharing_url="https://example.test/a-movie",
        trailer=DwTrailerRecord(
            dw_id="trailer-1",
            slug="a-movie-trailer",
            title="Official Trailer",
            sharing_url="https://example.test/a-movie-trailer",
        ),
    )

    def fail_output_path(*_args, **_kwargs):
        raise RuntimeError("output path failed")

    monkeypatch.setattr(service, "resolve_movie_output_path", fail_output_path)

    with pytest.raises(RuntimeError, match="output path failed"):
        service.create_movie_download(
            session,
            movie_data,
            MovieDownloadAPICreate(local_media_profile_id=profile.id),
        )
    session.rollback()

    assert session.query(Movie).count() == 0
    assert session.query(Trailer).count() == 0
    assert session.query(MovieMediaDownload).count() == 0

    session.close()
    engine.dispose()
