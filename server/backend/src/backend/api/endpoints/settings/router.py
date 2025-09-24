from fastapi import APIRouter, status

from .service import *
from ...models.settings import *
from backend.app import db_session

router = APIRouter()


@router.get("", response_model=SettingsAPIRead)
def settings_get():
    with db_session() as s:
        return get_settings(s)


@router.post("", response_model=SettingsAPIRead, status_code=status.HTTP_201_CREATED)
def settings_create(body: SettingsAPICreate):
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
    with db_session() as s:
        try:
            result = update_settings(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise