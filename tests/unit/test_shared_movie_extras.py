from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _movie_record(*, dw_id: str, slug: str, title: str, extras):
    from dailywire_api.records import DwMovieRecord

    return DwMovieRecord(
        dw_id=dw_id,
        slug=slug,
        title=title,
        sharing_url=f"https://www.dailywire.com/videos/{slug}",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="published",
        has_video=True,
        is_downloadable=True,
        movie_extras=list(extras),
        trailer=None,
    )


def test_same_dailywire_clip_can_belong_to_multiple_movies() -> None:
    """A Daily Wire clip listing is parent-scoped, not globally unique."""
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.movie_extras.service import sync_movie_extras
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieExtraRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        original = Movie(
            uuid="original-movie-uuid",
            type=MediaType.MOVIE.value,
            slug="run-hide-fight",
            title="Run Hide Fight",
            description=None,
            downloaded_date=None,
            duration=6540,
        )
        sequel = Movie(
            uuid="sequel-movie-uuid",
            type=MediaType.MOVIE.value,
            slug="run-hide-fight-infidels",
            title="Run Hide Fight: Infidels",
            description=None,
            downloaded_date=None,
            duration=0,
        )
        session.add_all([original, sequel])
        session.flush()

        shared_teaser = DwMovieExtraRecord(
            dw_id="f0f721fa-d187-4c16-8ccb-818fe794234c",
            slug="run-hide-fight-infidels",
            title="Run Hide Fight: Infidels | Teaser",
            movie_extra_type="trailer",
            duration=77.411633,
        )

        assert sync_movie_extras(
            session,
            movie=original,
            extras=[shared_teaser],
            official_trailer=None,
        ) == 1
        assert sync_movie_extras(
            session,
            movie=sequel,
            extras=[shared_teaser],
            official_trailer=None,
        ) == 1
        session.commit()

        rows = (
            session.query(MovieExtra)
            .filter(MovieExtra.slug == "run-hide-fight-infidels")
            .order_by(MovieExtra.movie_id)
            .all()
        )
        assert len(rows) == 2
        assert {row.movie_id for row in rows} == {original.id, sequel.id}
        assert {row.dw_id for row in rows} == {"f0f721fa-d187-4c16-8ccb-818fe794234c"}

        # Re-reading the same parent page still updates its existing listing
        # instead of creating a third row.
        assert sync_movie_extras(
            session,
            movie=sequel,
            extras=[shared_teaser],
            official_trailer=None,
        ) == 0
        session.commit()
        assert session.query(MovieExtra).filter(
            MovieExtra.slug == "run-hide-fight-infidels"
        ).count() == 2
    finally:
        session.close()
        engine.dispose()


def test_downloading_one_extra_survives_another_movies_shared_clip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Indexing all extras must not block a download because one clip is shared."""
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.media_downloads.service import create_movie_extra_download
    from backend.api.endpoints.movies.service import index_dailywire_movie
    from backend.api.models.media_download import MovieDownloadAPICreate
    from backend.db import Base
    from backend.db.models import MovieExtra, MovieLocalMediaProfile
    from backend.types.media_types import MediaType
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
            output_template="/downloads/movies/{{ movie_title }}/{{ title }}.ext",
            preferred_format="format_1080p",
            append_media_type_to_filename=False,
        )
        session.add(profile)
        session.flush()

        shared_teaser = DwMovieExtraRecord(
            dw_id="f0f721fa-d187-4c16-8ccb-818fe794234c",
            slug="run-hide-fight-infidels",
            title="Run Hide Fight: Infidels | Teaser",
            movie_extra_type="trailer",
            duration=77.411633,
        )
        final_trailer = DwMovieExtraRecord(
            dw_id="eb5b1a5f-771f-4c99-922a-55bdcb938193",
            slug="run-hide-fight-infidels-final-trailer",
            title="Run Hide Fight: Infidels | Final Trailer",
            movie_extra_type="trailer",
            duration=66.859422,
        )

        original = _movie_record(
            dw_id="5e1eb03f-5702-40ac-bece-b714a3a01f7b",
            slug="run-hide-fight",
            title="Run Hide Fight",
            extras=[shared_teaser],
        )
        index_dailywire_movie(session, original)
        session.flush()

        infidels = _movie_record(
            dw_id="b96f10fd-b2bc-4389-88d0-e4feefa62a8b",
            slug="run-hide-fight-infidels",
            title="Run Hide Fight: Infidels",
            extras=[final_trailer, shared_teaser],
        )
        download = create_movie_extra_download(
            session,
            infidels,
            final_trailer.slug,
            MovieDownloadAPICreate(local_media_profile_id=profile.id),
        )
        session.commit()

        downloaded_extra = session.get(MovieExtra, download.media_item_id)
        assert downloaded_extra is not None
        assert downloaded_extra.slug == "run-hide-fight-infidels-final-trailer"
        assert download.type == MediaType.MOVIE_EXTRA.value

        shared_rows = session.query(MovieExtra).filter(
            MovieExtra.dw_id == "f0f721fa-d187-4c16-8ccb-818fe794234c"
        ).all()
        assert len(shared_rows) == 2
        assert len({row.movie_id for row in shared_rows}) == 2
    finally:
        session.close()
        engine.dispose()
