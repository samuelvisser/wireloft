from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.settings import *
from backend.app import db_session
from backend.db.models import Settings

def get_settings() -> SettingsAPIRead:
    with db_session() as s:
        settings = (
            s.query(Settings)
            .first()
        )
        return SettingsAPIRead.model_validate(settings, from_attributes=True)


def create_settings_record(body: SettingsAPICreate) -> SettingsAPIRead:
    with db_session() as s:
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
        s.commit()
        s.refresh(settings)
        return SettingsAPIRead.model_validate(settings, from_attributes=True)


def update_settings(body: SettingsAPIUpdate) -> SettingsAPIRead:
    with db_session() as s:
        settings = (
            s.query(Settings)
            .one_or_none()
        )
        if settings is None:
            raise HTTPException(status_code=404, detail="Settings record not found")

        # Commit and return
        update_database_fields(settings, body)
        s.commit()
        s.refresh(settings)
        return SettingsAPIRead.model_validate(settings, from_attributes=True)
