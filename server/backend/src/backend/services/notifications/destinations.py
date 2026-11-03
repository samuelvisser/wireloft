"""Destinations and services: where messages go and what actions call, with their health and tests.

A destination's settings hold credentials, such as an Apprise URL or a media server's API key, so they are stored
encrypted and never shown again; the list shows a masked version.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import NotificationDestination, NotificationRule
from backend.security.crypto import decrypt_text, encrypt_text
from config.settings.base import get_config_path

from .apprise_services import InvalidDestination, masked_url, service_display_name, service_key_for_url


class Kind(StrEnum):
    APPRISE = "apprise"
    JELLYFIN = "jellyfin"
    EMBY = "emby"
    PLEX = "plex"
    WEBHOOK = "webhook"
    SCRIPT = "script"


MEDIA_SERVERS = frozenset({Kind.JELLYFIN, Kind.EMBY, Kind.PLEX})
ACTION_KINDS = MEDIA_SERVERS | {Kind.WEBHOOK, Kind.SCRIPT}
KIND_NAMES = {
    Kind.JELLYFIN: "Jellyfin", Kind.EMBY: "Emby", Kind.PLEX: "Plex", Kind.WEBHOOK: "Webhook", Kind.SCRIPT: "Script",
}


class DestinationNotFound(LookupError):
    pass


class Health(StrEnum):
    DISABLED = "disabled"
    FAILING = "failing"
    HEALTHY = "healthy"
    UNTESTED = "untested"


def scripts_folder() -> Path:
    """Scripts run only from here: WireLoft never stores a script itself."""
    return get_config_path().parent / "scripts"


def available_scripts() -> list[str]:
    folder = scripts_folder()
    if not folder.is_dir():
        return []
    return sorted(
        path.name for path in folder.iterdir()
        if path.is_file() and os.access(path, os.X_OK) and not path.name.startswith(".")
    )


def script_path(name: str) -> Path:
    """The script's path inside the scripts folder; anything else is refused."""
    folder = scripts_folder().resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise InvalidDestination(f"Choose a script from {scripts_folder()}")
    if not os.access(path, os.X_OK):
        raise InvalidDestination(f"{name} is not executable. Run chmod +x on it")
    return path


def _http_address(value: str, what: str, example: str) -> str:
    address = value.strip().rstrip("/")
    parts = urlsplit(address)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise InvalidDestination(f"{what} looks like {example}")
    return address


@dataclass(frozen=True)
class Checked:
    """A destination's settings after checking them, ready to store."""

    service: str
    config: dict[str, Any]
    masked: str


def check_config(kind: Kind, config: dict[str, Any]) -> Checked:
    """Check what was entered for a destination, and say what to show for it."""
    if kind == Kind.APPRISE:
        url = str(config.get("url") or "").strip()
        return Checked(service_key_for_url(url), {"url": url}, masked_url(url))
    if kind in MEDIA_SERVERS:
        address = _http_address(
            str(config.get("address") or ""), "The address", "http://plex:32400" if kind == Kind.PLEX else f"http://{kind.value}:8096",
        )
        key = str(config.get("api_key") or "").strip()
        if not key:
            raise InvalidDestination("Enter the Plex token" if kind == Kind.PLEX else "Enter an API key")
        scope = config.get("scope") or "folder"
        if scope not in {"folder", "library"}:
            raise InvalidDestination("Refresh the changed folder or the whole library")
        return Checked(kind.value, {
            "address": address, "api_key": key, "scope": scope,
            "path_from": str(config.get("path_from") or "").strip(), "path_to": str(config.get("path_to") or "").strip(),
        }, address)
    if kind == Kind.WEBHOOK:
        url = _http_address(str(config.get("url") or ""), "The webhook address", "https://example.com/hooks/wireloft")
        method = str(config.get("method") or "POST").upper()
        if method not in {"POST", "PUT"}:
            raise InvalidDestination("A webhook is sent with POST or PUT")
        header = str(config.get("secret_header") or "").strip()
        if header and not all(char.isalnum() or char == "-" for char in header):
            raise InvalidDestination("A header name has letters, digits and dashes only")
        parts = urlsplit(url)
        return Checked(kind.value, {
            "url": url, "method": method, "secret_header": header, "secret_value": str(config.get("secret_value") or ""),
        }, f"{method} {parts.scheme}://{parts.netloc}{parts.path}")
    if kind == Kind.SCRIPT:
        name = str(config.get("script") or "").strip()
        script_path(name)
        try:
            timeout = int(config.get("timeout_seconds") or 60)
        except (TypeError, ValueError):
            raise InvalidDestination("Enter the time limit in seconds") from None
        if not 1 <= timeout <= 3600:
            raise InvalidDestination("The time limit is between 1 second and an hour")
        return Checked(kind.value, {"script": name, "timeout_seconds": timeout}, f"{scripts_folder()}/{name}")
    raise InvalidDestination("Unknown kind of destination")


def config_of(destination: NotificationDestination) -> dict[str, Any] | None:
    decrypted = decrypt_text(destination.encrypted_config)
    return None if decrypted is None else json.loads(decrypted)


def _encrypted(config: dict[str, Any]) -> str:
    encrypted = encrypt_text(json.dumps(config))
    if encrypted is None:
        raise RuntimeError("WireLoft cannot protect the destination's settings")
    return encrypted.decode("ascii")


def health(destination: NotificationDestination) -> Health:
    if not destination.enabled:
        return Health.DISABLED
    if destination.consecutive_failures > 0:
        return Health.FAILING
    if destination.last_success_at is not None:
        return Health.HEALTHY
    return Health.UNTESTED


def display_service(destination: NotificationDestination) -> str:
    if destination.kind == Kind.APPRISE:
        return service_display_name(destination.service)
    return KIND_NAMES.get(Kind(destination.kind), destination.kind)


def get_destination(session: Session, destination_id: int) -> NotificationDestination:
    destination = session.get(NotificationDestination, destination_id)
    if destination is None:
        raise DestinationNotFound(destination_id)
    return destination


def list_destinations(session: Session) -> list[NotificationDestination]:
    return list(session.scalars(select(NotificationDestination).order_by(NotificationDestination.name)))


def create_destination(session: Session, *, kind: Kind, name: str, config: dict[str, Any]) -> NotificationDestination:
    checked = check_config(kind, config)
    destination = NotificationDestination(
        kind=kind.value, name=name.strip(), service=checked.service, encrypted_config=_encrypted(checked.config),
        masked=checked.masked[:255], enabled=True, consecutive_failures=0,
    )
    session.add(destination)
    session.flush()
    return destination


def update_destination(
    session: Session, destination_id: int, *, name: str | None = None, enabled: bool | None = None,
    config: dict[str, Any] | None = None,
) -> NotificationDestination:
    destination = get_destination(session, destination_id)
    if name is not None:
        destination.name = name.strip()
    if enabled is not None:
        destination.enabled = enabled
    if config is not None:
        checked = check_config(Kind(destination.kind), config)
        destination.service, destination.masked = checked.service, checked.masked[:255]
        destination.encrypted_config = _encrypted(checked.config)
        destination.last_status = destination.last_error = None
        destination.consecutive_failures = 0
    session.flush()
    return destination


def delete_destination(session: Session, destination_id: int) -> None:
    destination = get_destination(session, destination_id)
    for rule in session.scalars(select(NotificationRule)):
        if destination_id in (rule.destination_ids or []):
            rule.destination_ids = [value for value in rule.destination_ids if value != destination_id]
    session.delete(destination)
    session.flush()


def record_attempt(destination: NotificationDestination, *, delivered: bool, error: str | None) -> None:
    now = datetime.now(timezone.utc)
    destination.last_attempt_at = now
    if delivered:
        destination.last_status, destination.last_error = "SENT", None
        destination.last_success_at = now
        destination.consecutive_failures = 0
    else:
        destination.last_status, destination.last_error = "FAILED", (error or "")[:255]
        destination.consecutive_failures += 1


Purpose = Literal["message", "action"]


def purpose(kind: str) -> Purpose:
    return "action" if Kind(kind) in ACTION_KINDS else "message"
