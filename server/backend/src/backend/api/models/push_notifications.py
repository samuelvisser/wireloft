"""Validated Web Push registration and per-device options."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.services.push_notifications import CATEGORIES


class PushKeysInput(RequestBase):
    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=128)


class PushSubscriptionInput(RequestBase):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: PushKeysInput
    categories: set[str] = Field(default_factory=lambda: set(CATEGORIES))

    @model_validator(mode="after")
    def validate_push(self):
        from backend.services.push_notifications import validate_client_keys, validate_endpoint
        validate_endpoint(self.endpoint)
        validate_client_keys(self.keys.p256dh, self.keys.auth)
        if not self.categories.issubset(CATEGORIES):
            raise ValueError("Unknown notification category")
        return self


class PushSubscriptionLookup(RequestBase):
    endpoint: str = Field(min_length=10, max_length=2048)


class PushDeviceSettings(ResponseBase):
    enabled: bool
    categories: list[str]


class PushPublicKey(ResponseBase):
    public_key: str


class PushHistoryItem(ResponseBase):
    id: str
    title: str
    kind: str
    status: str
    source: str
    resource_type: str
    message: str | None
    notification_seen_at: datetime | None
    push_notified_at: datetime | None
    finished_at: datetime | None
