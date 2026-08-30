from backend.api.models.base import ResponseBase


class OnboardingStatusAPIRead(ResponseBase):
    """First-run onboarding state exposed to the authenticated UI."""

    completed: bool
    admin_password_configured: bool
