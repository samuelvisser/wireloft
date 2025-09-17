from fastapi import APIRouter, status

from .service import *
from ...models.settings import *

router = APIRouter()


@router.get("", response_model=list[SettingsAPIRead])
def settings_get():
    return get_settings()


@router.post("", response_model=SettingsAPIRead, status_code=status.HTTP_201_CREATED)
def settings_create(body: SettingsAPICreate):
   return create_settings_record(body)


@router.patch("/{setting_slug}", response_model=SettingsAPIRead)
def setting_update(body: SettingsAPIUpdate):
    return update_settings(body)