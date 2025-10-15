from __future__ import annotations

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records.UserInfo import UserInfo


def get_user_info() -> UserInfo:
    """
    Fetch the current user's information from the DailyWire middleware API
    and normalize it into the UserInfo model.
    """
    client = MiddlewareClient()
    payload = client.get_user_info()
    return UserInfo.model_validate(payload)
