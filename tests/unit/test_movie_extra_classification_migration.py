from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


PREVIOUS_REVISION = "d8f3a1c6b205"
REVISION = "e1c7a4b9d302"


def test_migration_repairs_official_trailer_classification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.db import core
    from backend.db.migrations import (
        get_alembic_config,
        get_current_revisions,
        upgrade_database,
    )

    database_path = tmp_path / "movie-extra-classification.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(core, "_engine", engine)
    monkeypatch.setattr(core, "_SessionLocal", session_factory)
    monkeypatch.setattr(core, "_db_path", database_path)

    command.upgrade(get_alembic_config(), PREVIOUS_REVISION)

    import backend.db.models  # noqa: F401
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType

    with Session(engine) as session:
        movie = Movie(
            uuid="movie-uuid",
            type=MediaType.MOVIE.value,
            slug="movie",
            title="Movie",
            description=None,
            duration=6000,
        )
        trailer = MovieExtra(
            movie=movie,
            uuid="trailer-uuid",
            type=MediaType.MOVIE_EXTRA.value,
            movie_extra_type="scene",
            slug="movie-official-trailer",
            title="Official Trailer",
            description=None,
            duration=90,
        )
        movie.official_trailer = trailer
        session.add(movie)
        session.commit()
        trailer_id = trailer.id

    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT movie_extra_type FROM media_items_movie_extra "
                "WHERE id = :trailer_id"
            ),
            {"trailer_id": trailer_id},
        ).scalar_one() == "scene"

    upgrade_database()

    assert get_current_revisions() == (REVISION,)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT movie_extra_type FROM media_items_movie_extra "
                "WHERE id = :trailer_id"
            ),
            {"trailer_id": trailer_id},
        ).scalar_one() == "trailer"

    engine.dispose()
