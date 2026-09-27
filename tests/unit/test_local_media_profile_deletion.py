from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _new_session(*, enforce_foreign_keys: bool = False) -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    if enforce_foreign_keys:
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    Base.metadata.create_all(engine)
    return Session(engine), engine


def _add_movie_download(
    session: Session,
    *,
    file_path: str = "/downloads/movies/movie.mp4",
    artifact_status: str = "absent",
):
    from backend.db.models import Movie, MovieLocalMediaProfile, MovieMediaDownload
    from backend.types.media_types import MediaType

    profile = MovieLocalMediaProfile(
        slug="movie-profile",
        name="Movie Profile",
        output_template="/downloads/movies/{{ movie_slug }}.ext",
        preferred_format="format_1080p",
    )
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="movie",
        title="Movie",
        extended_title="Movie",
        author_name="Director",
        mature_rating="PG-13",
        description=None,
        duration=3600,
    )
    download = MovieMediaDownload(
        media=movie,
        local_media_profile=profile,
        file_path=file_path,
        artifact_status=artifact_status,
    )
    session.add(download)
    session.commit()
    return profile, download


def test_delete_local_media_profile_removes_attached_download_without_file() -> None:
    from backend.api.endpoints.movie_local_media_profiles.service import (
        delete_movie_local_media_profile,
    )
    from backend.db.models import MovieLocalMediaProfile, MovieMediaDownload
    from backend.db.models.media_download import MediaDownloadHistory

    session, engine = _new_session(enforce_foreign_keys=True)
    try:
        profile, download = _add_movie_download(session)
        profile_id = profile.id
        download_id = download.id
        session.add(MediaDownloadHistory(
            media_download_id=download.id,
            action="created",
            event_metadata={},
        ))
        session.commit()

        delete_movie_local_media_profile(session, profile.slug)
        session.commit()

        assert session.get(MovieLocalMediaProfile, profile_id) is None
        assert session.get(MovieMediaDownload, download_id) is None
        assert (
            session.query(MediaDownloadHistory)
            .filter_by(media_download_id=download_id)
            .count()
            == 0
        )
    finally:
        session.close()
        engine.dispose()


def test_delete_local_media_profile_rejects_physical_file_even_when_status_is_absent(
    tmp_path: Path,
) -> None:
    from backend.api.endpoints.movie_local_media_profiles.service import (
        delete_movie_local_media_profile,
    )
    from backend.db.models import MovieLocalMediaProfile, MovieMediaDownload

    media_file = tmp_path / "movie.mp4"
    media_file.write_bytes(b"movie")

    session, engine = _new_session()
    try:
        profile, download = _add_movie_download(
            session,
            file_path=str(media_file),
            artifact_status="absent",
        )
        profile_id = profile.id
        download_id = download.id

        with pytest.raises(HTTPException) as exc_info:
            delete_movie_local_media_profile(session, profile.slug)

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail[0]
        assert detail["type"] == "resource_in_use"
        assert "physical file" in detail["msg"]
        assert "Delete all downloads" in detail["msg"]
        assert session.get(MovieLocalMediaProfile, profile_id) is not None
        assert session.get(MovieMediaDownload, download_id) is not None
        assert media_file.is_file()
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_delete_local_media_profile_allows_stale_available_row_when_file_is_gone(
    tmp_path: Path,
) -> None:
    from backend.api.endpoints.movie_local_media_profiles.service import (
        delete_movie_local_media_profile,
    )
    from backend.db.models import MovieLocalMediaProfile, MovieMediaDownload

    missing_file = tmp_path / "missing.mp4"

    session, engine = _new_session()
    try:
        profile, download = _add_movie_download(
            session,
            file_path=str(missing_file),
            artifact_status="available",
        )
        profile_id = profile.id
        download_id = download.id

        delete_movie_local_media_profile(session, profile.slug)
        session.commit()

        assert session.get(MovieLocalMediaProfile, profile_id) is None
        assert session.get(MovieMediaDownload, download_id) is None
    finally:
        session.close()
        engine.dispose()


def test_direct_profile_delete_never_nulls_required_download_foreign_key() -> None:
    from backend.db.models import MovieMediaDownload

    session, engine = _new_session(enforce_foreign_keys=True)
    profile, download = _add_movie_download(session)
    profile_id = profile.id
    download_id = download.id

    assert download in profile.media_downloads

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    session.delete(profile)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        session.flush()

    assert not any(
        "UPDATE media_downloads" in statement and "local_media_profile_id" in statement
        for statement in statements
    )

    session.rollback()
    persisted_download = session.get(MovieMediaDownload, download_id)
    assert persisted_download is not None
    assert persisted_download.local_media_profile_id == profile_id

    session.close()
    engine.dispose()
