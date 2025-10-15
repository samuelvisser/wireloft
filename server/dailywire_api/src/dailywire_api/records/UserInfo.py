from __future__ import annotations

from pydantic import Field, AliasChoices

from dailywire_api.records import BaseRecord

class UserInfo(BaseRecord):

    person_id: str = Field(validation_alias=AliasChoices('personId', 'personID'))
    subscription_id: str = Field(validation_alias=AliasChoices('subscriptionId', 'subscriptionID'))
    recurly_account_code: str
    username: str
    email: str
    first_name: str
    last_name: str
    avatar: str
    access_level: str
    plan_type: str
    account_created_at: str