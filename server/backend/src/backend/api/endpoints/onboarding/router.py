from fastapi import APIRouter

from backend.api.models.onboarding import OnboardingStatusAPIRead
from backend.app import db_session

from .service import complete_onboarding, get_onboarding_status


router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/status", response_model=OnboardingStatusAPIRead)
def onboarding_status():
    """Return whether the one-time first-run experience has been completed."""
    with db_session() as s:
        try:
            result = get_onboarding_status(s)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post("/complete", response_model=OnboardingStatusAPIRead)
def onboarding_complete():
    """Permanently mark the first-run experience as complete."""
    with db_session() as s:
        try:
            result = complete_onboarding(s)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
