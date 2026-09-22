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
