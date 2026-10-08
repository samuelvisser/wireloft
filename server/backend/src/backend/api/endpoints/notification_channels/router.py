"""Notification channel APIs are protected by the standard WireLoft authentication guard."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.endpoints.notification_channels.service import (
    channel_or_404, destination_url,
)
from backend.api.models.notification_channels import (
    ChannelCreateInput, ChannelOut, ChannelTestOut, ChannelUpdateInput, DeliveryOut,
    DestinationPreviewOut, DestinationTestInput, NotificationEventOut,
    NotificationServiceOut, RoutingInput,
)
from backend.services import notification_channels as channels
from backend.services.notification_events import EVENT_DEFINITIONS, NotificationEvent
from backend.services.notification_services import (
    masked_url, service_catalog, service_display_name, service_key_for_url,
)

router = APIRouter(prefix="/notifications", tags=["Notification channels"])


@router.get("/events", response_model=list[NotificationEventOut])
def list_events():
    return [NotificationEventOut.model_validate(definition) for definition in EVENT_DEFINITIONS]


@router.get("/services", response_model=list[NotificationServiceOut])
def list_services():
    return [NotificationServiceOut.model_validate(service) for service in service_catalog()]


@router.post("/destinations/preview", response_model=DestinationPreviewOut)
def preview_destination(body: DestinationTestInput):
    url = destination_url(body.destination)
    service = service_key_for_url(url)
    return DestinationPreviewOut(
        service=service, service_name=service_display_name(service), masked_url=masked_url(url),
    )


@router.post("/destinations/test", response_model=ChannelTestOut)
def test_destination(body: DestinationTestInput):
    return ChannelTestOut.model_validate(channels.send_test(destination_url(body.destination)))


@router.get("/channels", response_model=list[ChannelOut])
def list_channels():
    return [ChannelOut.model_validate(channel) for channel in channels.list_channels()]


@router.post("/channels", response_model=ChannelOut, status_code=201)
def create_channel(body: ChannelCreateInput):
    return ChannelOut.model_validate(channels.create_channel(
        name=body.name, url=destination_url(body.destination),
        events={NotificationEvent(event) for event in body.events},
    ))


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
def update_channel(channel_id: int, body: ChannelUpdateInput):
    url = destination_url(body.destination) if body.destination is not None else None
    with channel_or_404():
        return ChannelOut.model_validate(channels.update_channel(
            channel_id, name=body.name, enabled=body.enabled, url=url,
        ))


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int):
    with channel_or_404():
        channels.delete_channel(channel_id)


@router.post("/channels/{channel_id}/test", response_model=ChannelTestOut)
def test_channel(channel_id: int):
    with channel_or_404():
        return ChannelTestOut.model_validate(channels.send_test_to_channel(channel_id))


@router.put("/routing", response_model=list[ChannelOut])
def save_routing(body: RoutingInput):
    with channel_or_404():
        updated = channels.set_routes({
            route.channel_id: {NotificationEvent(event) for event in route.events} for route in body.routes
        })
    return [ChannelOut.model_validate(channel) for channel in updated]


@router.get("/deliveries", response_model=list[DeliveryOut])
def delivery_history(limit: int = 50):
    return [DeliveryOut.model_validate(record) for record in channels.delivery_history(limit)]
