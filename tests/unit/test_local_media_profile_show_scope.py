from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _new_session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


def test_show_local_media_profile_scope_defaults_to_both() -> None:
    from backend.api.endpoints.show_local_media_profiles.service import create_show_local_media_profile
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    session, engine = _new_session()
    profile = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(
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
    from backend.api.endpoints.show_local_media_profiles.service import create_show_local_media_profile
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate
    from backend.db.models import ShowLocalMediaProfile

    session, engine = _new_session()
    profile = create_show_local_media_profile(
        session,
        ShowLocalMediaProfileAPICreate(
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


def test_movie_local_media_profile_request_has_no_show_scope_field() -> None:
    from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPICreate

    assert "show_scope" not in MovieLocalMediaProfileAPICreate.model_fields
