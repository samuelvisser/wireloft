from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict


def _to_camel(s: str) -> str:
    # Convert snake_case (or already-camel) to camelCase
    if not s:
        return s
    parts = s.split('_')
    if len(parts) == 1:
        # already single token; just ensure lower first char
        return parts[0][0:1].lower() + parts[0][1:]
    return parts[0] + ''.join(p.capitalize() or '_' for p in parts[1:])


class ResponseModel(BaseModel):
    """Base class for API response models with camelCase JSON output via aliases."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
