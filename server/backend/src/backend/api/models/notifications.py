"""Messages and actions: destinations, rules, push devices and what was sent."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.services.notifications.destinations import Kind
from backend.services.notifications.events import Event

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
SummaryTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


# ---------- Requests ----------
class AppriseFieldsInput(RequestBase):
    """An Apprise destination described by a service and its form values."""

    mode: Literal["fields"]
    service: str = Field(min_length=1, max_length=64)
    values: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict, max_length=64)


class AppriseUrlInput(RequestBase):
    """An Apprise destination written directly as an Apprise URL."""

    mode: Literal["url"]
    url: str = Field(min_length=3, max_length=2048)


AppriseInput = Annotated[AppriseFieldsInput | AppriseUrlInput, Field(discriminator="mode")]


class MediaServerInput(RequestBase):
    address: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=512)
    scope: Literal["folder", "library"] = "folder"
    path_from: str = Field(default="", max_length=1024)
    path_to: str = Field(default="", max_length=1024)


class WebhookInput(RequestBase):
    url: str = Field(min_length=1, max_length=2048)
    method: Literal["POST", "PUT"] = "POST"
    secret_header: str = Field(default="", max_length=80)
    secret_value: str = Field(default="", max_length=1024)


class ScriptInput(RequestBase):
    script: str = Field(min_length=1, max_length=255)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)


class DestinationInput(RequestBase):
    """The settings of one destination; only the part for its kind is used."""

    kind: Kind
    apprise: AppriseInput | None = None
    media_server: MediaServerInput | None = None
    webhook: WebhookInput | None = None
    script: ScriptInput | None = None

    @model_validator(mode="after")
    def _has_settings(self):
        part = {
            Kind.APPRISE: self.apprise, Kind.JELLYFIN: self.media_server, Kind.EMBY: self.media_server,
            Kind.PLEX: self.media_server, Kind.WEBHOOK: self.webhook, Kind.SCRIPT: self.script,
        }[self.kind]
        if part is None:
            raise ValueError("Fill in the destination's settings")
        return self


class DestinationCreate(RequestBase):
    name: Name
    destination: DestinationInput


class DestinationUpdate(RequestBase):
    name: Name | None = None
    enabled: bool | None = None
    destination: DestinationInput | None = None


class DestinationTest(RequestBase):
    destination: DestinationInput


class RuleInput(RequestBase):
    enabled: bool = True
    event: Event
    show_scope: Literal["any", "chosen"] = "any"
    show_ids: list[int] = Field(default_factory=list, max_length=500)
    push: bool = False
    destination_ids: list[int] = Field(default_factory=list, max_length=50)
    delivery: Literal["now", "grouped", "daily"] = "now"
    summary_time: SummaryTime = "08:00"

    @model_validator(mode="after")
    def _sensible(self):
        if self.event == Event.EVERYTHING and self.delivery != "daily":
            raise ValueError("Everything that happens only goes out in a daily summary")
        if self.show_scope == "chosen" and not self.show_ids:
            raise ValueError("Choose at least one show")
        return self


class PushKeys(RequestBase):
    p256dh: str = Field(min_length=16, max_length=256)
    auth: str = Field(min_length=8, max_length=128)


class PushSubscriptionInput(RequestBase):
    endpoint: str = Field(min_length=8, max_length=2048)
    keys: PushKeys
    device_name: str = Field(default="This device", max_length=80)


class PushEndpointInput(RequestBase):
    endpoint: str = Field(min_length=8, max_length=2048)


# ---------- Responses ----------
class EventRead(ResponseBase):
    event: str
    when: str
    tone: str
    shows: bool
    actions: bool
    problem: bool


class ServiceFieldChoiceRead(ResponseBase):
    value: str
    label: str


class ServiceFieldRead(ResponseBase):
    key: str
    label: str
    kind: str
    required: bool
    advanced: bool
    choices: list[ServiceFieldChoiceRead]
    default: str | None


class AppriseServiceRead(ResponseBase):
    key: str
    name: str
    service_url: str | None
    setup_url: str | None
    fields: list[ServiceFieldRead]


class DestinationPreviewRead(ResponseBase):
    service: str
    service_name: str
    masked: str


class DestinationRead(ResponseBase):
    id: int
    kind: str
    purpose: Literal["message", "action"]
    name: str
    service: str
    service_name: str
    masked: str
    enabled: bool
    health: str
    last_error: str | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    settings: dict[str, Any] = Field(default_factory=dict)
    """The settings that are not secret, to fill the form when editing."""


class TestRead(ResponseBase):
    delivered: bool
    error: str | None
    elapsed_ms: int


class RuleRead(ResponseBase):
    id: int
    default_key: str | None
    enabled: bool
    event: str
    show_scope: str
    show_ids: list[int]
    push: bool
    destination_ids: list[int]
    delivery: str
    summary_time: str


class ScriptsRead(ResponseBase):
    folder: str
    scripts: list[str]
    variables: list[str]


class DeliveryRead(ResponseBase):
    id: int
    title: str
    event: str
    destination: str
    status: str
    error: str | None
    at: datetime
    retry_at: datetime | None = None
    """When a failed attempt is tried again; set only while it is waiting for that."""


class DeviceRead(ResponseBase):
    id: int
    device_name: str
    created_at: datetime


class PushDeviceStatusRead(ResponseBase):
    subscribed: bool
    device_id: int | None = None


class VapidKeyRead(ResponseBase):
    public_key: str


class WebhookExampleRead(ResponseBase):
    payload: dict[str, Any]
