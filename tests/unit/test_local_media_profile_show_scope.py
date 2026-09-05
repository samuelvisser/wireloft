from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _new_session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def test_show_local_media_profile_scope_defaults_to_both() -> None:
    from backend.api.endpoints.local_media_profiles.service import create_local_media_profile
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    session, engine = _new_session()
    profile = create_local_media_profile(
        session,
        LocalMediaProfileAPICreate(
            type="show",
            name="Show audio",
            output_template="/downloads/shows/{{ show }}/{{ episode_title }}.ext",
            preferred_format="format_audio_only",
        ),
    )

    assert profile.show_scope == "both"

    session.close()
    engine.dispose()


def test_show_local_media_profile_scope_is_persisted_and_returned() -> None:
    from backend.api.endpoints.local_media_profiles.service import create_local_media_profile
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate
    from backend.db.models import ShowLocalMediaProfile

    session, engine = _new_session()
    profile = create_local_media_profile(
        session,
        LocalMediaProfileAPICreate(
            type="show",
            show_scope="podcast",
            name="Podcast audio",
            output_template="/downloads/podcasts/{{ show }}/{{ episode_title }}.ext",
            preferred_format="format_audio_only",
        ),
    )

    stored = session.query(ShowLocalMediaProfile).filter_by(id=profile.id).one()
    assert stored.show_scope == "podcast"
    assert profile.show_scope == "podcast"

    session.close()
    engine.dispose()


def test_movie_local_media_profiles_reject_show_scope() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    with pytest.raises(ValidationError, match="Show availability"):
        LocalMediaProfileAPICreate(
            type="movie",
            show_scope="series",
            name="Movie video",
            output_template="/downloads/movies/{{ movie_title }}/{{ title }}.ext",
            preferred_format="format_1080p",
        )
