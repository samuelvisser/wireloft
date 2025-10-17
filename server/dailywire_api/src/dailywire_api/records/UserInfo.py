from __future__ import annotations

from typing import Union

from dailywire_api.records import BaseRecord
from dailywire_api.types.user_info import DwMembershipLevel


class UserInfo(BaseRecord):

    person_id: str
    subscription_id: str
    recurly_account_code: str
    username: str
    email: str
    first_name: str
    last_name: str
    avatar: str
    access_level: Union[DwMembershipLevel, str]
    plan_type: str
    account_created_at: str