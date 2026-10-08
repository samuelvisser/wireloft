"""HTTP-facing helpers for notification channels."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from backend.api.models.notification_channels import DestinationFieldsInput, DestinationInput
from backend.services.notification_channels import ChannelNotFound
from backend.services.notification_services import InvalidDestination, build_url, parse_destination


def invalid_destination(message: str) -> HTTPException:
    """A validation error shown beneath the destination section of the form."""
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", "destination"], "msg": message, "type": "value_error"}],
    )


def destination_url(destination: DestinationInput) -> str:
    """Turn the submitted destination into a validated Apprise URL."""
    try:
        url = (
            build_url(destination.service, destination.values)
            if isinstance(destination, DestinationFieldsInput)
            else destination.url.strip()
        )
        parse_destination(url)
    except InvalidDestination as error:
        raise invalid_destination(str(error)) from error
    return url


@contextmanager
def channel_or_404() -> Iterator[None]:
    try:
        yield
    except ChannelNotFound as error:
        raise HTTPException(status_code=404, detail="Notification channel not found") from error
