from __future__ import annotations

from pydantic import Field

from dailywire_api.records import BaseRecord

class UserInfo(BaseRecord):

    person_id: str
    recurly_account_code: str
    email: str
    first_name: str
    last_name: str
    avatar: str
    username: str
    access_level: str
    account_created_at: str
    plan_type: str
    subscription_id: str = Field(validation_alias='subscriptionId')