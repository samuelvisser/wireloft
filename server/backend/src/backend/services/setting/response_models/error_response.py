from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error payload."""

    error: str
