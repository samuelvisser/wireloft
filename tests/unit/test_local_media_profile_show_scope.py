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



def test_updating_show_scope_keeps_the_saved_subtitle_choice() -> None:
    from backend.api.endpoints.show_local_media_profiles.service import (
        create_show_local_media_profile,
        update_show_local_media_profile,
    )
    from backend.api.models.show_local_media_profile import (
        ShowLocalMediaProfileAPICreate,
        ShowLocalMediaProfileAPIUpdate,
    )
    from backend.db.models import ShowLocalMediaProfile

    template = "/downloads/shows/{{ show }}/{{ episode_title }}.ext"

    for initial_scope, initial_mode, new_scope in (
        ("podcast", "no_subtitles", "series"),
        ("series", "sidecar", "podcast"),
        ("both", "embed_and_sidecar", "podcast"),
    ):
        session, engine = _new_session()
        try:
            created = create_show_local_media_profile(
                session,
                ShowLocalMediaProfileAPICreate(
                    name="Scope subtitles",
                    preferred_format="format_1080p",
                    show_scope=initial_scope,
                    subtitle_mode=initial_mode,
                    output_template=template,
                ),
            )
            update = ShowLocalMediaProfileAPIUpdate(
                name=created.name,
                preferred_format="format_1080p",
                show_scope=new_scope,
                output_template=template,
            )
            assert "subtitle_mode" not in update.model_fields_set

            updated = update_show_local_media_profile(session, created.slug, update)

            assert updated.show_scope == new_scope
            assert updated.subtitle_mode == initial_mode
            stored = session.get(ShowLocalMediaProfile, created.id)
            assert stored is not None
            assert stored.subtitle_mode == initial_mode
        finally:
            session.close()
            engine.dispose()


def test_explicit_subtitle_selection_still_updates_existing_show_profile() -> None:
    from backend.api.endpoints.show_local_media_profiles.service import (
        create_show_local_media_profile,
        update_show_local_media_profile,
    )
    from backend.api.models.show_local_media_profile import (
        ShowLocalMediaProfileAPICreate,
        ShowLocalMediaProfileAPIUpdate,
    )
    from backend.db.models import ShowLocalMediaProfile

    session, engine = _new_session()
    try:
        template = "/downloads/shows/{{ show }}/{{ episode_title }}.ext"
        created = create_show_local_media_profile(
            session,
            ShowLocalMediaProfileAPICreate(
                name="Explicit subtitles", preferred_format="format_1080p",
                show_scope="podcast", output_template=template,
            ),
        )
        assert created.subtitle_mode == "no_subtitles"

        update = ShowLocalMediaProfileAPIUpdate(
            name=created.name, preferred_format="format_1080p",
            show_scope="series", subtitle_mode="embed",
            output_template=template,
        )
        assert "subtitle_mode" in update.model_fields_set

        updated = update_show_local_media_profile(session, created.slug, update)
        assert updated.show_scope == "series"
        assert updated.subtitle_mode == "embed"
        assert session.get(ShowLocalMediaProfile, created.id).subtitle_mode == "embed"
    finally:
        session.close()
        engine.dispose()


def test_movie_update_without_subtitle_mode_preserves_saved_choice() -> None:
    from backend.api.endpoints.movie_local_media_profiles.service import (
        create_movie_local_media_profile,
        update_movie_local_media_profile,
    )
    from backend.api.models.movie_local_media_profile import (
        MovieLocalMediaProfileAPICreate,
        MovieLocalMediaProfileAPIUpdate,
    )
    from backend.db.models import MovieLocalMediaProfile

    session, engine = _new_session()
    try:
        template = "/downloads/movies/{{ movie_title }}/{{ title }}.ext"
        created = create_movie_local_media_profile(
            session,
            MovieLocalMediaProfileAPICreate(
                name="Movie subtitles", preferred_format="format_1080p",
                subtitle_mode="embed_and_sidecar", output_template=template,
            ),
        )
        update = MovieLocalMediaProfileAPIUpdate(
            name=created.name, preferred_format="format_720p",
            output_template=template,
        )
        assert "subtitle_mode" not in update.model_fields_set
        updated = update_movie_local_media_profile(session, created.slug, update)
        assert updated.preferred_format == "format_720p"
        assert updated.subtitle_mode == "embed_and_sidecar"
        assert session.get(MovieLocalMediaProfile, created.id).subtitle_mode == "embed_and_sidecar"
    finally:
        session.close()
        engine.dispose()
