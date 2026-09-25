from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _new_session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def test_aggregate_local_media_profiles_are_validated_before_session_closes() -> None:
    from backend.api.endpoints.local_media_profiles.service import (
        get_local_media_profile,
        get_local_media_profiles_list,
    )
    from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPIRead
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPIRead
    from backend.db.models import MovieLocalMediaProfile, ShowLocalMediaProfile

    session, engine = _new_session()
    try:
        session.add_all([
            ShowLocalMediaProfile(
                slug="show-profile",
                name="Show profile",
                show_scope="series",
                output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
                preferred_format="format_1080p",
            ),
            MovieLocalMediaProfile(
                slug="movie-profile",
                name="Movie profile",
                output_template="/downloads/movies/{{ movie_title }}/{{ title }}.ext",
                preferred_format="format_1080p",
            ),
        ])
        session.commit()

        profiles = get_local_media_profiles_list(session)
        show_profile = get_local_media_profile(session, "show-profile")
    finally:
        session.close()
        engine.dispose()

    assert isinstance(profiles[0], ShowLocalMediaProfileAPIRead)
    assert profiles[0].show_scope == "series"
    assert isinstance(profiles[1], MovieLocalMediaProfileAPIRead)
    assert isinstance(show_profile, ShowLocalMediaProfileAPIRead)
    assert show_profile.show_scope == "series"



def test_local_media_profile_view_reports_managed_download_statistics() -> None:
    from backend.api.endpoints.local_media_profiles.service import get_local_media_profile_view
    from backend.db.models import Movie, MovieLocalMediaProfile, MovieMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    session, engine = _new_session()
    try:
        profile = MovieLocalMediaProfile(
            slug="movie-profile",
            name="Movie profile",
            output_template="/downloads/movies/{{ movie_title }}/{{ title }}.ext",
            preferred_format="format_1080p",
        )
        downloaded_movie = Movie(
            uuid="downloaded-movie",
            type=MediaType.MOVIE.value,
            slug="downloaded",
            title="Downloaded",
            extended_title="Downloaded",
            author_name="Director",
            mature_rating="PG",
            description=None,
            duration=60,
        )
        pending_movie = Movie(
            uuid="pending-movie",
            type=MediaType.MOVIE.value,
            slug="pending",
            title="Pending",
            extended_title="Pending",
            author_name="Director",
            mature_rating="PG",
            description=None,
            duration=60,
        )
        session.add_all([
            MovieMediaDownload(
                media=downloaded_movie,
                local_media_profile=profile,
                file_path="/downloads/movies/downloaded.mp4",
                artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
                artifact_size_bytes=1024,
                downloaded_bytes=2048,
            ),
            MovieMediaDownload(
                media=pending_movie,
                local_media_profile=profile,
                file_path="/downloads/movies/pending.ext",
                artifact_status=MediaDownloadArtifactStatus.ABSENT.value,
            ),
        ])
        session.commit()

        view = get_local_media_profile_view(session, profile.slug)

        assert view.profile.id == profile.id
        assert view.statistics.managed_media_count == 2
        assert view.statistics.downloaded_media_count == 1
        assert view.statistics.storage_size_bytes == 2048
        assert view.statistics.download_profile_count == 0
    finally:
        session.close()
        engine.dispose()
