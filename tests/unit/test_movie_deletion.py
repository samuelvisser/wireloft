from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_delete_movie_uses_download_cleanup_and_preserves_completed_files(tmp_path):
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.movies.service import delete_movie
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieLocalMediaProfile
    from backend.db.models.media_download import (
        MediaDownloadBase,
        MovieMediaDownload,
        MovieExtraMediaDownload,
    )
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        active_profile = MovieLocalMediaProfile(
            slug="active-movies",
            name="Active Movies",
            output_template="/downloads/active/{title}.ext",
            preferred_format="format_1080p",
        )
        completed_profile = MovieLocalMediaProfile(
            slug="completed-movies",
            name="Completed Movies",
            output_template="/downloads/completed/{title}.ext",
            preferred_format="format_720p",
        )
        movie = Movie(
            uuid="movie-delete-uuid",
            type=MediaType.MOVIE.value,
            slug="movie-to-delete",
            title="Movie To Delete",
            description=None,
            downloaded_date=None,
            duration=100,
        )
        trailer = MovieExtra(
            uuid="trailer-delete-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie=movie,
            movie_extra_type="trailer",
            slug="movie-to-delete-trailer",
            title="Movie To Delete Trailer",
            description=None,
            downloaded_date=None,
            duration=10,
        )
        session.add_all([active_profile, completed_profile, movie, trailer])
        session.flush()

        movie_path = tmp_path / "movie.mp4"
        trailer_path = tmp_path / "trailer.mp4"
        completed_path = tmp_path / "completed.mp4"
        active_artifacts = [
            movie_path,
            tmp_path / "movie.mp4.part",
            trailer_path,
            tmp_path / "trailer.mp4.rawts",
            tmp_path / "trailer.mp4.rawts.part",
        ]
        for artifact in [*active_artifacts, completed_path]:
            artifact.write_bytes(b"download data")

        session.add_all([
            MovieMediaDownload(
                type=MediaType.MOVIE.value,
                media_item_id=movie.id,
                local_media_profile_id=active_profile.id,
                download_status=MediaDownloadStatus.DOWNLOADING.value,
                file_path=str(movie_path),
                progress=50,
            ),
            MovieExtraMediaDownload(
                type=MediaType.MOVIE_EXTRA.value,
                media_item_id=trailer.id,
                local_media_profile_id=active_profile.id,
                download_status=MediaDownloadStatus.LOCAL_PROCESSING.value,
                file_path=str(trailer_path),
                progress=100,
            ),
            MovieMediaDownload(
                type=MediaType.MOVIE.value,
                media_item_id=movie.id,
                local_media_profile_id=completed_profile.id,
                download_status=MediaDownloadStatus.DOWNLOADED.value,
                file_path=str(completed_path),
                progress=100,
            ),
        ])
        session.commit()

        payload = delete_movie(session, movie.slug)
        session.commit()

        assert payload.slug == "movie-to-delete"
        assert session.query(Movie).count() == 0
        assert session.query(MovieExtra).count() == 0
        assert session.query(MediaDownloadBase).count() == 0
        assert all(not artifact.exists() for artifact in active_artifacts)
        assert completed_path.exists()
    finally:
        session.close()
        engine.dispose()
