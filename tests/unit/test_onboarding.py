from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_onboarding_status_creates_the_single_settings_row(monkeypatch):
    from backend.api.endpoints.onboarding import service
    from backend.db import Base
    from backend.db.models import Settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(admin_auth=SimpleNamespace(enabled=True)),
    )

    with Session(engine) as session:
        status = service.get_onboarding_status(session)
        session.commit()

        assert status.completed is False
        assert status.admin_password_configured is True
        [settings] = session.query(Settings).all()
        assert settings.onboarding_completed is False

    engine.dispose()


def test_complete_onboarding_is_persistent(monkeypatch):
    from backend.api.endpoints.onboarding import service
    from backend.db import Base
    from backend.db.models import Settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(admin_auth=SimpleNamespace(enabled=False)),
    )

    with Session(engine) as session:
        status = service.complete_onboarding(session)
        session.commit()

        assert status.completed is True
        assert status.admin_password_configured is False
        assert session.query(Settings).one().onboarding_completed is True

    with Session(engine) as session:
        assert service.get_onboarding_status(session).completed is True

    engine.dispose()
