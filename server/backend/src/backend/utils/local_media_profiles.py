from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.models import LocalMediaProfileBase
from backend.types.local_media_profile_types import LocalMediaProfileType


def require_local_media_profile_type(
    session: Session,
    profile_id: int,
    expected_type: LocalMediaProfileType,
) -> LocalMediaProfileBase:
    profile = session.get(LocalMediaProfileBase, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Local media profile not found")
    if profile.type != expected_type.value:
        label = expected_type.value.title()
        raise HTTPException(
            status_code=422,
            detail=f"This operation requires a {label} Local Media Profile",
        )
    return profile
