"""API models for Apprise notification channels, event routing and delivery history."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.services.notification_events import DEFAULT_EVENTS, NotificationEvent

ChannelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


# ---------- Requests ----------
class DestinationFieldsInput(RequestBase):
    """A destination described by a service and its form values."""

    mode: Literal["fields"]
    service: str = Field(min_length=1, max_length=64)
    values: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict, max_length=64)


class DestinationUrlInput(RequestBase):
    """A destination written directly as an Apprise URL."""

    mode: Literal["url"]
    url: str = Field(min_length=3, max_length=2048)


DestinationInput = Annotated[DestinationFieldsInput | DestinationUrlInput, Field(discriminator="mode")]


class ChannelCreateInput(RequestBase):
    name: ChannelName
    destination: DestinationInput
    events: set[NotificationEvent] = Field(default_factory=lambda: set(DEFAULT_EVENTS))


class ChannelUpdateInput(RequestBase):
    name: ChannelName | None = None
    enabled: bool | None = None
    destination: DestinationInput | None = None

    @model_validator(mode="after")
    def require_a_change(self):
        if self.name is None and self.enabled is None and self.destination is None:
            raise ValueError("Nothing to update")
        return self


class DestinationTestInput(RequestBase):
    destination: DestinationInput


class RouteInput(RequestBase):
    channel_id: int
    events: set[NotificationEvent]


class RoutingInput(RequestBase):
    routes: list[RouteInput] = Field(max_length=200)


# ---------- Responses ----------
class NotificationEventOut(ResponseBase):
    event: str
    label: str
    description: str
    tone: str


class ServiceFieldChoiceOut(ResponseBase):
    value: str
    label: str


class ServiceFieldOut(ResponseBase):
    key: str
    label: str
    kind: str
    required: bool
    advanced: bool
    choices: list[ServiceFieldChoiceOut]
    default: str | None


class NotificationServiceOut(ResponseBase):
    key: str
    name: str
    service_url: str | None
    setup_url: str | None
    fields: list[ServiceFieldOut]


class DestinationPreviewOut(ResponseBase):
    service: str
    service_name: str
    masked_url: str


class ChannelOut(ResponseBase):
    id: int
    name: str
    service: str
    service_name: str
    masked_url: str
    enabled: bool
    health: str
    last_error: str | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    events: list[str]


class ChannelTestOut(ResponseBase):
    delivered: bool
    error: str | None
    elapsed_ms: int


class DeliveryOut(ResponseBase):
    id: str
    operation_id: str
    title: str
    event: str
    destination: str
    status: str
    error: str | None
    at: datetime
