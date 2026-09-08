from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_upcoming_movie_allows_extras_but_not_full_movie(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import (
        create_movie_download,
        create_movie_extra_download,
    )
    from backend.api.endpoints.movies import service as movie_service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import MovieLocalMediaProfile
    from backend.db.models.media_download import MovieExtraMediaDownload
    from config import get_settings
    from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(movie_service, "ensure_movie_release_metadata", lambda _s, _movie: None)

    profile = MovieLocalMediaProfile(
        slug="movies",
        name="Movies",
        output_template="/downloads/{{ movie_title }}/{{ slug }}.ext",
        preferred_format="format_1080p",
    )
    session.add(profile)
    session.commit()

    trailer = DwMovieExtraRecord(
        dw_id="trailer-1",
        slug="upcoming-movie-final-trailer",
        title="Upcoming Movie | Final Trailer",
        movie_extra_type="trailer",
        duration=67,
        sharing_url="https://www.dailywire.com/clips/upcoming-movie-final-trailer",
    )
    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="upcoming-movie",
        title="Upcoming Movie | Final Trailer",
        description="Upcoming movie description.",
        duration=0,
        sharing_url="https://www.dailywire.com/videos/upcoming-movie",
        status="scheduled",
        published_at=datetime(2026, 9, 16, 5, 8, tzinfo=timezone.utc),
        has_video=False,
        is_downloadable=False,
        movie_extras=[trailer],
        trailer=trailer,
    )
    body = MovieDownloadAPICreate(local_media_profile_id=profile.id)

    assert movie_data.is_upcoming is True

    with pytest.raises(HTTPException) as exc_info:
        create_movie_download(session, movie_data, body)
    assert exc_info.value.status_code == 422

    extra_download = create_movie_extra_download(
        session,
        movie_data,
        trailer.slug,
        body,
    )
    session.commit()

    assert isinstance(extra_download, MovieExtraMediaDownload)
    assert extra_download.media.slug == trailer.slug

    session.close()
    engine.dispose()
