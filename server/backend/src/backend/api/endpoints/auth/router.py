from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, Response, status, HTTPException

from backend.security.auth import (
    verify_admin_password,
    set_session_cookie,
    clear_session_cookie,
    is_authenticated,
)

router = APIRouter(tags=["auth"], prefix="/auth")


class LoginInput(BaseModel):
    password: str = Field(min_length=7)


@router.get("/status")
async def auth_status(request: Request):
    if is_authenticated(request):
        return {"authenticated": True}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def password_login(data: LoginInput, response: Response):
    if not verify_admin_password(data.password):
        # Provide a server error in FastAPI format with field-level mapping
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[{"loc": ["body", "password"], "msg": "Incorrect password", "type": "value_error"}],
        )
    set_session_cookie(response)
    # Do not return a new Response object; returning here allows FastAPI to
    # use the provided 'response' with the Set-Cookie header attached.
    return


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    clear_session_cookie(response)
    # Same here: let FastAPI send the provided 'response' that contains the
    # cookie deletion header.
    return
