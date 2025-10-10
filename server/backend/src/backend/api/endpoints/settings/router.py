from fastapi import APIRouter, status

from .service import *
from ...models.settings import *
from backend.app import db_session

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=SettingsAPIRead)
def settings_get():
    """
    Retrieve current system settings.

    Returns the current configuration settings for the application.
    """
    with db_session() as s:
        return get_settings(s)


@router.post("", response_model=SettingsAPIRead, status_code=status.HTTP_201_CREATED)
def settings_create(body: SettingsAPICreate):
    """
    Initialize system settings.

    Creates the initial settings record. This is typically called once during setup.
    Returns the created settings configuration.
    """
    with db_session() as s:
        try:
            result = create_settings_record(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.patch("/{setting_slug}", response_model=SettingsAPIRead)
def setting_update(setting_slug: str, body: SettingsAPIUpdate):
    """
    Update system settings.

    Partially updates system configuration with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_settings(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise