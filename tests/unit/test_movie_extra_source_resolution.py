from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_movie_extra_construction_reuses_source_without_call_site_awareness() -> None:
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.types.media_types import MediaType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        movies = [
            Movie(
                uuid=f"movie-{index}-uuid",
                type=MediaType.MOVIE.value,
                slug=f"movie-{index}",
                title=f"Movie {index}",
                description=None,
                duration=6000,
            )
            for index in (1, 2)
        ]
        session.add_all(movies)
        session.flush()

        first = MovieExtra(
            movie=movies[0],
            uuid="extra-a-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie_extra_type="featurette",
            slug="shared-extra",
            title="Original title",
            description="Useful description",
            duration=90,
            thumbnail_landscape_path="original.jpg",
            available_for=["ALL_ACCESS"],
        )
        second = MovieExtra(
            movie=movies[1],
            uuid="extra-b-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie_extra_type="scene",
            slug="shared-extra",
            title="Updated title",
            description=None,
            duration=0,
            thumbnail_landscape_path=None,
            available_for=[],
        )

        session.add_all([first, second])
        session.flush()

        source = session.query(MovieExtraSource).one()
        assert first.source is source
        assert second.source is source
        assert first.source_id == second.source_id == source.id
        assert source.slug == "shared-extra"
        assert source.title == "Updated title"
        assert source.description == "Useful description"
        assert source.duration == 90
        assert source.thumbnail_landscape_path == "original.jpg"
        assert source.available_for == ["ALL_ACCESS"]

    engine.dispose()


def test_movie_extra_construction_reuses_already_persisted_source() -> None:
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.types.media_types import MediaType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        source = MovieExtraSource(
            slug="persisted-extra",
            title="Persisted title",
            description="Persisted description",
            duration=30,
        )
        movie = Movie(
            uuid="movie-uuid",
            type=MediaType.MOVIE.value,
            slug="movie",
            title="Movie",
            description=None,
            duration=6000,
        )
        session.add_all([source, movie])
        session.commit()

        extra = MovieExtra(
            movie=movie,
            uuid="extra-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie_extra_type="interview",
            slug="persisted-extra",
            title="Refreshed title",
            description=None,
            duration=0,
        )
        session.add(extra)
        session.flush()

        assert session.query(MovieExtraSource).count() == 1
        assert extra.source_id == source.id
        assert extra.title == "Refreshed title"
        assert extra.description == "Persisted description"
        assert extra.duration == 30

    engine.dispose()
