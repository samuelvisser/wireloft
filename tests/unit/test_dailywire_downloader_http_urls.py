from __future__ import annotations

from types import SimpleNamespace


def test_http_get_encodes_raw_spaces_without_touching_existing_percent_encoding(monkeypatch) -> None:
    import dailywire_downloader.http as http_module

    requested_urls: list[str] = []

    class FakeResponse:
        status = 200
        headers = {}

        def read(self) -> bytes:
            return b""

        def close(self) -> None:
            pass

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(http_module, "urlopen", fake_urlopen)

    raw_url = (
        "https://daily-wire-production.imgix.net/clips/example/"
        "John Matthews Thumbnail.png?auto=compress&cs=origin"
    )
    encoded_url = (
        "https://daily-wire-production.imgix.net/clips/example/"
        "John%20Matthews%20Thumbnail.png?auto=compress&cs=origin"
    )

    with http_module.http_get(raw_url, retries=0):
        pass
    with http_module.http_get(encoded_url, retries=0):
        pass

    assert requested_urls == [encoded_url, encoded_url]


def test_movie_extra_sync_preserves_encoded_thumbnail_url() -> None:
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.movie_extras.service import sync_movie_extras
    from backend.db import Base
    from backend.db.models import Movie, MovieExtraSource
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieExtraRecord
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        movie = Movie(
            uuid="movie-url-preservation",
            type=MediaType.MOVIE.value,
            slug="movie-url-preservation",
            title="Movie URL Preservation",
            description=None,
            duration=100,
        )
        session.add(movie)
        session.flush()

        thumbnail_url = (
            "https://daily-wire-production.imgix.net/clips/example/"
            "John%20Matthews%20Thumbnail.png?auto=compress&cs=origin"
        )
        extra = DwMovieExtraRecord(
            slug="extra-url-preservation",
            title="Extra URL Preservation",
            thumbnail_landscape_path=thumbnail_url,
        )

        sync_movie_extras(
            session,
            movie=movie,
            extras=[extra],
            official_trailer=None,
        )
        session.commit()

        source = session.query(MovieExtraSource).one()
        assert source.thumbnail_landscape_path == thumbnail_url
    finally:
        session.close()
        engine.dispose()
