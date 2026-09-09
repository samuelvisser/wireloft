from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _movie_record(slug: str, title: str, extra):
    from dailywire_api.records import DwMovieRecord

    return DwMovieRecord(
        dw_id=f"rotating-{slug}-id",
        slug=slug,
        title=title,
        sharing_url=f"https://www.dailywire.com/videos/{slug}",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="published",
        has_video=True,
        is_downloadable=True,
        movie_extras=[extra],
        trailer=None,
    )


def test_deleting_one_movie_preserves_shared_source_other_placement_and_download(
    tmp_path,
    monkeypatch,
) -> None:
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.media_downloads.service import create_movie_extra_download
    from backend.api.endpoints.movies.service import delete_movie
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource, MovieLocalMediaProfile
    from backend.db.models.media_download import MovieExtraMediaDownload
    from config import get_settings
    from dailywire_api.records import DwMovieExtraRecord

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        profile = MovieLocalMediaProfile(
            slug="movies",
            name="Movies",
            output_template="/downloads/{{ movie_title }}/{{ slug }}.ext",
            preferred_format="format_1080p",
        )
        session.add(profile)
        session.flush()

        shared = DwMovieExtraRecord(
            dw_id="rotating-shared-id",
            slug="shared-extra",
            title="Shared Extra",
            movie_extra_type="trailer",
            duration=60,
        )
        movie_a = _movie_record("movie-a", "Movie A", shared)
        movie_b = _movie_record("movie-b", "Movie B", shared)
        body = MovieDownloadAPICreate(local_media_profile_id=profile.id)

        download_a = create_movie_extra_download(session, movie_a, shared.slug, body)
        download_b = create_movie_extra_download(session, movie_b, shared.slug, body)
        session.commit()

        source_id = session.query(MovieExtraSource.id).scalar()
        movie_b_row = session.query(Movie).filter_by(slug="movie-b").one()
        movie_b_extra = movie_b_row.movie_extras[0]
        movie_b_download_id = download_b.id

        delete_movie(session, "movie-a")
        session.commit()

        assert session.query(Movie).filter_by(slug="movie-a").count() == 0
        assert session.query(Movie).filter_by(slug="movie-b").count() == 1
        assert session.query(MovieExtraSource).count() == 1
        assert session.get(MovieExtraSource, source_id).slug == "shared-extra"
        assert session.query(MovieExtra).count() == 1
        remaining_extra = session.query(MovieExtra).one()
        assert remaining_extra.id == movie_b_extra.id
        assert remaining_extra.source_id == source_id

        assert session.query(MovieExtraMediaDownload).count() == 1
        remaining_download = session.query(MovieExtraMediaDownload).one()
        assert remaining_download.id == movie_b_download_id
        assert remaining_download.media_item_id == remaining_extra.id
        assert download_a.id != remaining_download.id
    finally:
        session.close()
        engine.dispose()
