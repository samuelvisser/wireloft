from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session


def test_content_metadata_is_stored_by_concrete_owner_and_transparent_to_callers():
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Movie, MovieExtra, MovieExtraSource
    from backend.db.models.media_item import MediaItemBase
    from backend.types.media_types import MediaType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        movie = Movie(
            uuid="movie-uuid",
            type=MediaType.MOVIE.value,
            slug="movie-a",
            title="Movie A",
            description="Movie description",
            downloaded_date=None,
            duration=5400,
            background_image_path="movie-background.jpg",
            thumbnail_landscape_path="movie-landscape.jpg",
            thumbnail_portrait_path="movie-portrait.jpg",
            thumbnail_square_path="movie-square.jpg",
        )
        source = MovieExtraSource(
            slug="shared-extra",
            title="Shared Extra",
            description="One canonical description",
            duration=90,
            background_image_path="extra-background.jpg",
            thumbnail_landscape_path="extra-landscape.jpg",
            thumbnail_portrait_path="extra-portrait.jpg",
            thumbnail_square_path="extra-square.jpg",
        )
        extra = MovieExtra(
            uuid="extra-placement-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie=movie,
            source=source,
            movie_extra_type="trailer",
            downloaded_date=None,
        )
        session.add_all([movie, extra])
        session.commit()

        inspector = inspect(engine)
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
        assert content_fields <= {
            column["name"] for column in inspector.get_columns("episodes")
        }
        assert content_fields <= {
            column["name"] for column in inspector.get_columns("movies")
        }
        assert content_fields <= {
            column["name"] for column in inspector.get_columns("movie_extra_sources")
        }
        assert {column["name"] for column in inspector.get_columns("movie_extras")} == {
            "id",
            "movie_id",
            "source_id",
            "movie_extra_type",
        }

        assert extra.title == "Shared Extra"
        assert extra.description == "One canonical description"
        assert extra.duration == 90
        assert extra.thumbnail_landscape_path == "extra-landscape.jpg"
        assert session.query(MovieExtra).filter(
            MovieExtra.slug == "shared-extra"
        ).one().id == extra.id
        assert session.query(MovieExtra).filter(
            MovieExtra.title == "Shared Extra"
        ).one().id == extra.id

        # Every source-owned field behaves like a normal MovieExtra attribute.
        proxy_updates = {
            "slug": "renamed-shared-extra",
            "title": "Renamed Shared Extra",
            "description": "Updated canonical description",
            "duration": 120,
            "background_image_path": "updated-background.jpg",
            "thumbnail_landscape_path": "updated-landscape.jpg",
            "thumbnail_portrait_path": "updated-portrait.jpg",
            "thumbnail_square_path": "updated-square.jpg",
            "sharing_url": "https://example.test/renamed-shared-extra",
            "published_date": datetime(2026, 9, 9, tzinfo=timezone.utc),
            "available_for": ["ALL_ACCESS"],
        }
        for field, value in proxy_updates.items():
            setattr(extra, field, value)
        session.flush()

        for field, value in proxy_updates.items():
            assert getattr(extra, field) == value
            assert getattr(source, field) == value

        assert session.query(MovieExtra).filter(
            MovieExtra.slug == "renamed-shared-extra"
        ).one().id == extra.id
        assert session.query(MovieExtra).filter(
            MovieExtra.title == "Renamed Shared Extra"
        ).one().id == extra.id

        # Generic callers still receive polymorphic objects exposing the same
        # public metadata API even though the physical owner differs by subtype.
        media = session.query(MediaItemBase).order_by(MediaItemBase.id).all()
        assert [(item.type, item.title) for item in media] == [
            (MediaType.MOVIE.value, "Movie A"),
            (MediaType.MOVIE_EXTRA.value, "Renamed Shared Extra"),
        ]
    finally:
        session.close()
        engine.dispose()
