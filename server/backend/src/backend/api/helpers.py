from fastapi import HTTPException

from pydantic import BaseModel as APIModel
from backend.db import Base as DatabaseModel


def update_database_fields(db_model: DatabaseModel, data: APIModel) -> None:

    updates = data.model_dump(by_alias=True)
    for field, value in updates.items():
        if not hasattr(db_model, field):
            raise HTTPException(status_code=422, detail=f"Field {field} does not exist in database")
        setattr(db_model, field, value)