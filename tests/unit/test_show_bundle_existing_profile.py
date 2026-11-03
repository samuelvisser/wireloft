from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session():
    from backend.db.core import Base
    import backend.api.endpoints.shows.router  # noqa: F401  (loads every model first)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()
    engine.dispose()


def test_a_show_bundle_can_use_an_existing_profile(session):
    from backend.api.endpoints.shows.as_bundle import service
    from backend.api.models.show_as_bundle import ShowAPICreateBundle
    from backend.db.models import Show, ShowLocalMediaProfile

    template = "/downloads/shows/{{ show_title }}/{{ season_name }}/{{ episode_title }}.ext"
    session.add(ShowLocalMediaProfile(slug="shows", name="Shows", preferred_format="format_1080p", output_template=template))
    session.commit()
    show = {
        "uuid": "show-uuid", "slug": "a-show", "title": "A show", "description": None,
        "sharingUrl": "https://www.dailywire.com/show/a-show", "membershipLevel": "FREE", "type": "series",
        "episodeIdentifier": "seasonal", "authorName": "A Host", "authorSlug": "a-host",
    }
    profile = {
        "op": "update_by_slug", "slug": "shows", "name": "Shows", "preferredFormat": "format_1080p",
        "outputTemplate": template, "indexingValues": [],
    }
    created = service.create_show_bundle(
        session, None, ShowAPICreateBundle.model_validate({"show": show, "seasons": [], "localMediaProfile": profile}),
    )
    assert session.get(Show, created.id) is not None
    assert session.query(ShowLocalMediaProfile).count() == 1
