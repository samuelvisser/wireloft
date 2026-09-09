from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session


def test_shared_source_owns_all_intrinsic_movie_extra_metadata() -> None:
    """Parent placements retain only per-movie state while metadata is global."""
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.movie_extras.service import sync_movie_extras
    from backend.api.models.movie_extra import MovieExtraAPIRead
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieExtraRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        movie_a = Movie(
            uuid="movie-a-uuid",
            type=MediaType.MOVIE.value,
            slug="movie-a",
            title="Movie A",
            description=None,
            duration=6000,
        )
        movie_b = Movie(
            uuid="movie-b-uuid",
            type=MediaType.MOVIE.value,
            slug="movie-b",
            title="Movie B",
            description=None,
            duration=6100,
        )
        session.add_all([movie_a, movie_b])
        session.flush()

        published_at = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)
        shared_for_a = DwMovieExtraRecord(
            dw_id="rotating-id-a",
            slug="shared-extra",
            title="Shared Extra",
            description="Canonical clip description",
            duration=91.5,
            movie_extra_type="trailer",
            background_image_path="background.jpg",
            thumbnail_landscape_path="landscape.jpg",
            thumbnail_portrait_path="portrait.jpg",
            thumbnail_square_path="square.jpg",
            sharing_url="https://www.dailywire.com/videos/shared-extra",
            published_date=published_at,
            available_for=["ALL_ACCESS"],
        )
        # The same clip may be classified differently under another parent. That
        # classification is placement metadata and must not move onto the source.
        shared_for_b = shared_for_a.model_copy(update={
            "dw_id": "rotating-id-b",
            "movie_extra_type": "scene",
            # Simulate a parent page that omits a field another page supplied.
            "description": None,
        })

        assert sync_movie_extras(
            session,
            movie=movie_a,
            extras=[shared_for_a],
            official_trailer=None,
        ) == 1
        assert sync_movie_extras(
            session,
            movie=movie_b,
            extras=[shared_for_b],
            official_trailer=None,
        ) == 1
        session.commit()

        source = session.query(MovieExtraSource).one()
        assert source.slug == "shared-extra"
        assert source.title == "Shared Extra"
        assert source.description == "Canonical clip description"
        assert source.duration == 91.5
        assert source.background_image_path == "background.jpg"
        assert source.thumbnail_landscape_path == "landscape.jpg"
        assert source.thumbnail_portrait_path == "portrait.jpg"
        assert source.thumbnail_square_path == "square.jpg"
        assert source.sharing_url == "https://www.dailywire.com/videos/shared-extra"
        assert source.published_date == published_at
        assert source.available_for == ["ALL_ACCESS"]
        assert not hasattr(source, "dw_id")

        placements = session.query(MovieExtra).order_by(MovieExtra.movie_id).all()
        assert len(placements) == 2
        assert {placement.source_id for placement in placements} == {source.id}
        assert {placement.movie_extra_type for placement in placements} == {"trailer", "scene"}
        assert all(placement.title == source.title for placement in placements)
        assert all(placement.description == source.description for placement in placements)
        assert all(placement.duration == source.duration for placement in placements)
        assert all(placement.sharing_url == source.sharing_url for placement in placements)
        assert all(placement.published_date == source.published_date for placement in placements)
        assert all(placement.available_for == source.available_for for placement in placements)

        # The joined-inheritance child table now contains only placement data.
        inspector = inspect(engine)
        assert {
            column["name"]
            for column in inspector.get_columns("media_items_movie_extra")
        } == {"id", "movie_id", "source_id", "movie_extra_type"}

        # MediaItemBase owns identity only. Intrinsic clip metadata exists once,
        # on MovieExtraSource, rather than being duplicated per placement.
        content_fields = {
            "title",
            "description",
            "duration",
            "background_image_path",
            "thumbnail_landscape_path",
            "thumbnail_portrait_path",
            "thumbnail_square_path",
        }
        assert content_fields.isdisjoint(
            {column["name"] for column in inspector.get_columns("media_items")}
        )

        api_extra = MovieExtraAPIRead.model_validate(placements[0])
        assert api_extra.slug == source.slug
        assert api_extra.title == source.title
        assert api_extra.description == source.description
        assert api_extra.duration == source.duration
        assert api_extra.thumbnail_landscape_path == source.thumbnail_landscape_path
        assert api_extra.available_for == source.available_for
    finally:
        session.close()
        engine.dispose()


def test_refreshing_one_parent_updates_global_metadata_for_every_placement() -> None:
    """A source refresh is immediately reflected by all parents sharing it."""
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.movie_extras.service import sync_movie_extras
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.types.media_types import MediaType
    from dailywire_api.records import DwMovieExtraRecord

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        movies = [
            Movie(
                uuid=f"movie-{index}-uuid",
                type=MediaType.MOVIE.value,
                slug=f"movie-{index}",
                title=f"Movie {index}",
                description=None,
                duration=5000,
            )
            for index in (1, 2)
        ]
        session.add_all(movies)
        session.flush()

        original = DwMovieExtraRecord(
            slug="shared-featurette",
            title="Original title",
            description="Original description",
            movie_extra_type="featurette",
            duration=30,
        )
        for movie in movies:
            sync_movie_extras(
                session,
                movie=movie,
                extras=[original],
                official_trailer=None,
            )
        session.commit()

        placements = session.query(MovieExtra).order_by(MovieExtra.movie_id).all()
        assert len({placement.source_id for placement in placements}) == 1
        placement_ids = [placement.id for placement in placements]

        refreshed = original.model_copy(update={
            "dw_id": "a-new-rotating-id",
            "title": "Updated global title",
            "description": "Updated global description",
            "duration": 45,
            "thumbnail_landscape_path": "updated.jpg",
        })
        assert sync_movie_extras(
            session,
            movie=movies[1],
            extras=[refreshed],
            official_trailer=None,
        ) == 0
        session.commit()
        session.expire_all()

        source = session.query(MovieExtraSource).one()
        assert source.title == "Updated global title"
        assert source.description == "Updated global description"
        assert source.duration == 45
        assert source.thumbnail_landscape_path == "updated.jpg"

        reloaded = session.query(MovieExtra).order_by(MovieExtra.movie_id).all()
        assert [placement.id for placement in reloaded] == placement_ids
        assert [placement.title for placement in reloaded] == [
            "Updated global title",
            "Updated global title",
        ]
        assert [placement.description for placement in reloaded] == [
            "Updated global description",
            "Updated global description",
        ]
    finally:
        session.close()
        engine.dispose()
