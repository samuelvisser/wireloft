from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_failed_lookup_uses_conditional_path_and_creates_download(tmp_path, monkeypatch):
    from backend.api.endpoints.media_downloads.service import create_movie_download
    from backend.api.endpoints.movies import service as movie_service
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db.core import Base
    from backend.db.models import Movie, MovieLocalMediaProfile
    from backend.db.models.media_download import MediaDownloadBase
    from backend.integrations.tmdb import MovieReleaseLookupResult
    from config import get_settings
    from dailywire_api.records import DwMovieRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(
        movie_service,
        "lookup_movie_release_metadata",
        lambda **_kwargs: MovieReleaseLookupResult(
            status="not_found",
            attempted_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            error="No confident TMDB movie match was found",
        ),
    )

    profile = MovieLocalMediaProfile(
        slug="plex-movies",
        name="Plex movies",
        output_template=(
            "/downloads/{{ movie_title }}{% if year %} ({{ year }}){% endif %}/{{ title }}.ext"
        ),
        preferred_format="format_1080p",
        append_media_type_to_filename=False,
    )
    session.add(profile)
    session.commit()

    movie_data = DwMovieRecord(
        dw_id="movie-1",
        slug="unknown-movie",
        title="Unknown Movie",
        duration=6000,
        sharing_url="https://www.dailywire.com/videos/unknown-movie",
        is_downloadable=True,
    )

    download = create_movie_download(
        session,
        movie_data,
        MovieDownloadAPICreate(local_media_profile_id=profile.id),
    )
    session.commit()

    movie = session.query(Movie).one()
    assert movie.release_date is None
    assert movie.release_date_lookup_status == "not_found"
    assert movie.release_date_lookup_attempted_at is not None
    assert movie.release_date_lookup_error == "No confident TMDB movie match was found"
    assert session.query(MediaDownloadBase).count() == 1
    assert download.file_path == str(tmp_path / "Unknown Movie" / "Unknown Movie.ext")

    session.close()
    engine.dispose()
