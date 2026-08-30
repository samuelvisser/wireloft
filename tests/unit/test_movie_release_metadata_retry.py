from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _movie_with_lookup_error(session):
    from backend.db.models import Movie
    from backend.types.media_types import MediaType

    movie = Movie(
        uuid="movie-retry-uuid",
        type=MediaType.MOVIE.value,
        slug="retry-movie",
        title="Retry Movie",
        description="A movie whose first metadata request failed.",
        duration=6000,
        release_date_lookup_status="error",
        release_date_lookup_attempted_at=datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc),
        release_date_lookup_error="TMDB request failed with HTTP 503",
    )
    session.add(movie)
    session.commit()
    return movie


def test_retry_movie_release_metadata_can_recover_from_transient_error(monkeypatch):
    from backend.api.endpoints.movies import service as movie_service
    from backend.db.core import Base
    from backend.integrations.tmdb import MovieReleaseLookupResult

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _movie_with_lookup_error(session)

    monkeypatch.setattr(
        movie_service,
        "lookup_movie_release_metadata",
        lambda **_kwargs: MovieReleaseLookupResult(
            status="matched",
            attempted_at=datetime(2026, 8, 30, 8, 5, tzinfo=timezone.utc),
            release_date=date(2020, 9, 10),
            source="tmdb",
            source_id="1234",
        ),
    )

    result = movie_service.retry_movie_release_metadata(session, "retry-movie")

    assert result.release_date == date(2020, 9, 10)
    assert result.release_date_lookup_status == "matched"
    assert result.release_date_lookup_error is None
    assert result.release_date_source == "tmdb"
    assert result.release_date_source_id == "1234"

    session.close()
    engine.dispose()


def test_retry_movie_release_metadata_persists_another_transient_error(monkeypatch):
    from backend.api.endpoints.movies import service as movie_service
    from backend.db.core import Base
    from backend.integrations.tmdb import MovieReleaseLookupResult

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    _movie_with_lookup_error(session)
    retried_at = datetime(2026, 8, 30, 8, 10, tzinfo=timezone.utc)

    monkeypatch.setattr(
        movie_service,
        "lookup_movie_release_metadata",
        lambda **_kwargs: MovieReleaseLookupResult(
            status="error",
            attempted_at=retried_at,
            error="TMDB request failed with HTTP 502",
        ),
    )

    result = movie_service.retry_movie_release_metadata(session, "retry-movie")

    assert result.release_date is None
    assert result.release_date_lookup_status == "error"
    assert result.release_date_lookup_attempted_at == retried_at
    assert result.release_date_lookup_error == "TMDB request failed with HTTP 502"

    session.close()
    engine.dispose()


def test_retry_movie_release_metadata_is_only_available_for_error_status():
    from backend.api.endpoints.movies import service as movie_service
    from backend.db.core import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    movie = _movie_with_lookup_error(session)
    movie.release_date_lookup_status = "ambiguous"
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        movie_service.retry_movie_release_metadata(session, "retry-movie")

    assert exc_info.value.status_code == 409

    session.close()
    engine.dispose()
