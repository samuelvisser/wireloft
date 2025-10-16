from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.settings import *
from backend.db.models import Settings

def get_settings(s: Session) -> SettingsAPIRead:
    settings = (
        s.query(Settings)
        .first()
    )
    return SettingsAPIRead.model_validate(settings)


def create_settings_record(s: Session, body: SettingsAPICreate) -> SettingsAPIRead:
    settings = (
        s.query(Settings)
        .one_or_none()
    )
    if settings is not None:
        raise HTTPException(status_code=409, detail="Settings record already exists")

    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    settings = Settings(**data)
    s.add(settings)
    s.flush()
    return SettingsAPIRead.model_validate(settings)


def update_settings(s: Session, body: SettingsAPIUpdate) -> SettingsAPIRead:
    settings: Optional[Settings] = (
        s.query(Settings)
        .one_or_none()
    )
    if settings is None:
        raise HTTPException(status_code=404, detail="Settings record not found")

    # Apply updates and flush; commit in router
    update_database_fields(settings, body)
    s.flush()
    return SettingsAPIRead.model_validate(settings)
