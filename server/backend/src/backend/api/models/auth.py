from backend.api.models.base import RequestBase, ResponseBase


class LoginInput(RequestBase):
    """Input for login endpoint"""

    passwordHash: str


class AuthResponse(ResponseBase):
    """Response for authentication status"""

    authenticated: bool