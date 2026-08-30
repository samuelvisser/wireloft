from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_pending_movie_gets_one_lookup_after_tmdb_is_configured(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import (
        create_movie_download,
        create_movie_extra_download,
    )
    from backend.api.endpoints.movies import service as movie_service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, MovieLocalMediaProfile
    from backend.integrations.tmdb import MovieReleaseLookupResult
    from config import get_settings
    from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    configured = False
    actual_lookups = []

    def fake_lookup(*, title, description=None, duration_seconds=0):
        if not configured:
            return None
        actual_lookups.append(title)
        return MovieReleaseLookupResult(
            status="matched",
            attempted_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            release_date=date(2020, 9, 10),
            source="tmdb",
            source_id="718444",
        )

    monkeypatch.setattr(movie_service, "lookup_movie_release_metadata", fake_lookup)

    profiles = [
        MovieLocalMediaProfile(
            slug=f"movies-{index}",
            name=f"Movies {index}",
            output_template=f"/downloads/profile-{index}/{{title}}.ext",
            preferred_format="format_1080p",
            append_media_type_to_filename=True,
        )
        for index in range(3)
    ]
    session.add_all(profiles)
    session.commit()

    official_trailer = DwMovieExtraRecord(
        dw_id="trailer-1",
        slug="run-hide-fight-trailer",
        title="Official Trailer",
        movie_extra_type="trailer",
        sharing_url="https://www.dailywire.com/clips/run-hide-fight-trailer",
        duration=120,
    )
    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="run-hide-fight",
        title="Run Hide Fight",
        duration=109 * 60,
        sharing_url="https://www.dailywire.com/videos/run-hide-fight",
        is_downloadable=True,
        movie_extras=[official_trailer],
        trailer=official_trailer,
    )

    create_movie_download(
        session,
        movie_data,
        MovieDownloadAPICreate(local_media_profile_id=profiles[0].id),
    )
    session.commit()
    movie = session.query(Movie).one()
    assert movie.release_date_lookup_attempted_at is None
    assert actual_lookups == []

    configured = True
    create_movie_extra_download(
        session,
        movie_data,
        "run-hide-fight-trailer",
        MovieDownloadAPICreate(local_media_profile_id=profiles[1].id),
    )
    session.commit()
    assert actual_lookups == ["Run Hide Fight"]
    assert movie.release_date == date(2020, 9, 10)

    create_movie_download(
        session,
        movie_data,
        MovieDownloadAPICreate(local_media_profile_id=profiles[2].id),
    )
    session.commit()
    assert actual_lookups == ["Run Hide Fight"]

    session.close()
    engine.dispose()
