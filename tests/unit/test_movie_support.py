from __future__ import annotations

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


def test_create_movie_download_persists_movie_and_uses_local_profile(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import create_movie_download, get_media_downloads_view
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import LocalMediaProfile, Movie
    from backend.db.models.media_download import MovieMediaDownload
    from config import get_settings
    from dailywire_api.records import DwMovieRecord, DwTrailerRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    profile = LocalMediaProfile(
        slug="movies",
        name="Movies",
        output_template="/downloads/{movie_title}/{movie}.ext",
        preferred_format="format_1080p",
    )
    session.add(profile)
    session.commit()

    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="a-movie",
        title="A Movie",
        description="Movie description",
        duration=5400,
        sharing_url="https://www.dailywire.com/videos/a-movie",
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
    assert movie.slug == "a-movie"
    assert movie.trailer_slug == "a-movie-trailer"
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
