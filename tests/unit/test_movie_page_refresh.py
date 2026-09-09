from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _movie_record(*, status: str, downloadable: bool, title: str):
    from dailywire_api.records import DwMovieRecord

    return DwMovieRecord(
        dw_id="movie-1",
        slug="refresh-me",
        title=title,
        description="Movie description",
        duration=5400 if downloadable else 0,
        sharing_url="https://www.dailywire.com/videos/refresh-me",
        has_video=downloadable,
        is_downloadable=downloadable,
        status=status,
    )


def test_refresh_dailywire_movie_updates_existing_movie_without_creating_another():
    from backend.api.endpoints.movies.service import index_dailywire_movie, refresh_dailywire_movie
    from backend.db.core import Base
    from backend.db.models import Movie

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    movie, created = index_dailywire_movie(
        session,
        _movie_record(status="scheduled", downloadable=False, title="Old upcoming title"),
    )
    session.commit()
    movie_id = movie.id

    result = refresh_dailywire_movie(
        session,
        "refresh-me",
        _movie_record(status="published", downloadable=True, title="Current published title"),
    )
    session.commit()

    assert created is True
    assert result.id == movie_id
    assert result.title == "Current published title"
    assert result.status == "published"
    assert result.is_downloadable is True
    assert session.query(Movie).count() == 1

    session.close()
    engine.dispose()


def test_refresh_dailywire_movie_requires_an_indexed_movie():
    import pytest
    from fastapi import HTTPException

    from backend.api.endpoints.movies.service import refresh_dailywire_movie
    from backend.db.core import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    with pytest.raises(HTTPException) as exc_info:
        refresh_dailywire_movie(
            session,
            "refresh-me",
            _movie_record(status="published", downloadable=True, title="Published title"),
        )

    assert exc_info.value.status_code == 404

    session.close()
    engine.dispose()
