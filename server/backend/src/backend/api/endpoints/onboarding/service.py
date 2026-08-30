from __future__ import annotations

from sqlalchemy.orm import Session

from backend.api.models.onboarding import OnboardingStatusAPIRead
from backend.db.models import Settings
from config import get_settings


def _get_or_create_settings(s: Session) -> Settings:
    settings = s.query(Settings).order_by(Settings.id).first()
    if settings is None:
        settings = Settings(onboarding_completed=False)
        s.add(settings)
        s.flush()
    return settings


def _as_response(settings: Settings) -> OnboardingStatusAPIRead:
    return OnboardingStatusAPIRead(
        completed=settings.onboarding_completed,
        admin_password_configured=get_settings().admin_auth.enabled,
    )


def get_onboarding_status(s: Session) -> OnboardingStatusAPIRead:
    return _as_response(_get_or_create_settings(s))


def complete_onboarding(s: Session) -> OnboardingStatusAPIRead:
    settings = _get_or_create_settings(s)
    settings.onboarding_completed = True
    s.flush()
    return _as_response(settings)
