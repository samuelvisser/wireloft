"""Talking to destinations: sending a message, refreshing a media server, calling a webhook, running a script."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from backend.db.models import NotificationDestination
from backend.db.models import NotificationEvent as EventRow

from .apprise_services import InvalidDestination, parse_destination
from .destinations import Kind, script_path
from .events import DEFINITIONS, Event, Tone

logger = logging.getLogger(__name__)

ERROR_LIMIT = 200
_TIMEOUT_SECONDS = 15
_URL_IN_TEXT = re.compile(r"\S+://\S+")
_LOG_PREFIX = re.compile(r"^\d{4}-\d\d-\d\d [\d:,]+ - [A-Z]+ - ")


@dataclass(frozen=True)
class Outcome:
    delivered: bool
    error: str | None = None
    retry: bool = True
    """False when trying again cannot help, such as a fault in WireLoft itself."""


def _short(error: str) -> str:
    return _URL_IN_TEXT.sub("[address]", error)[:ERROR_LIMIT]


def send_message(config: dict[str, Any], *, title: str, body: str, tone: Tone) -> Outcome:
    """Send a message through Apprise."""
    from apprise import LogCapture, NotifyType

    url = config["url"]
    try:
        plugin = parse_destination(url)
    except InvalidDestination as error:
        return Outcome(False, str(error)[:ERROR_LIMIT])
    notify_type = {Tone.SUCCESS: NotifyType.SUCCESS, Tone.FAILURE: NotifyType.FAILURE}.get(tone, NotifyType.INFO)
    try:
        with LogCapture(level=logging.WARNING) as capture:
            delivered = plugin.notify(body=body or title, title=title, notify_type=notify_type)
            log = capture.getvalue()
    except Exception as error:  # Apprise plugins talk to arbitrary services.
        return Outcome(False, f"The service could not be reached ({type(error).__name__})")
    if delivered:
        return Outcome(True)
    lines = [_LOG_PREFIX.sub("", line.strip()) for line in log.splitlines() if line.strip()]
    return Outcome(False, _short((lines[-1] if lines else "The service did not accept the message").replace(url, "[destination]")))


def _mapped(path: str, config: dict[str, Any]) -> str:
    """The path as the media server sees it."""
    source, target = config.get("path_from") or "", config.get("path_to") or ""
    if source and path.startswith(source):
        return target + path[len(source):]
    return path


def _request(method: str, url: str, **kwargs) -> Outcome:
    try:
        response = requests.request(method, url, timeout=_TIMEOUT_SECONDS, allow_redirects=False, **kwargs)
    except requests.RequestException as error:
        return Outcome(False, f"Could not reach it ({type(error).__name__})")
    if response.status_code in (401, 403):
        return Outcome(False, "It refused the API key or token")
    if response.status_code >= 400:
        return Outcome(False, f"It answered with HTTP {response.status_code}")
    return Outcome(True)


def _jellyfin_refresh(config: dict[str, Any], folders: Sequence[str]) -> Outcome:
    headers = {"X-Emby-Token": config["api_key"]}
    if config["scope"] == "library" or not folders:
        return _request("POST", f"{config['address']}/Library/Refresh", headers=headers)
    updates = [{"Path": _mapped(folder, config), "UpdateType": "Modified"} for folder in folders]
    return _request("POST", f"{config['address']}/Library/Media/Updated", headers=headers, json={"Updates": updates})


def _plex_sections(config: dict[str, Any]) -> list[tuple[str, list[str]]]:
    response = requests.get(
        f"{config['address']}/library/sections", headers={"Accept": "application/json", "X-Plex-Token": config["api_key"]},
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    directories = response.json().get("MediaContainer", {}).get("Directory", [])
    return [
        (str(directory.get("key")), [str(location.get("path")) for location in directory.get("Location", [])])
        for directory in directories
    ]


def _plex_refresh(config: dict[str, Any], folders: Sequence[str]) -> Outcome:
    headers = {"X-Plex-Token": config["api_key"]}
    if config["scope"] == "library" or not folders:
        return _request("GET", f"{config['address']}/library/sections/all/refresh", headers=headers)
    try:
        sections = _plex_sections(config)
    except (requests.RequestException, ValueError) as error:
        return Outcome(False, f"Could not list Plex's libraries ({type(error).__name__})")
    for folder in folders:
        path = _mapped(folder, config)
        section = next((key for key, locations in sections if any(path.startswith(location) for location in locations)), None)
        if section is None:
            return Outcome(False, f"No Plex library holds {path}. Check the path mapping")
        outcome = _request("GET", f"{config['address']}/library/sections/{section}/refresh?path={quote(path)}", headers=headers)
        if not outcome.delivered:
            return outcome
    return Outcome(True)


def refresh_media_server(kind: Kind, config: dict[str, Any], folders: Sequence[str]) -> Outcome:
    return _plex_refresh(config, folders) if kind == Kind.PLEX else _jellyfin_refresh(config, folders)


def webhook_payload(event: EventRow) -> dict[str, Any]:
    """The exact JSON a webhook receives, also shown in the webhook's form."""
    return {
        "event": event.event,
        "title": event.title,
        "message": event.body,
        "occurredAt": event.occurred_at.isoformat() if event.occurred_at else None,
        "url": event.url,
        **{key: value for key, value in (event.data or {}).items() if key in WEBHOOK_FIELDS},
    }


WEBHOOK_FIELDS = ("show", "episode", "filePath", "folder")


def call_webhook(config: dict[str, Any], payload: dict[str, Any]) -> Outcome:
    headers = {"Content-Type": "application/json", "User-Agent": "WireLoft"}
    if config.get("secret_header"):
        headers[config["secret_header"]] = config.get("secret_value") or ""
    return _request(config["method"], config["url"], headers=headers, data=json.dumps(payload))


def script_environment(event: EventRow) -> dict[str, str]:
    """The variables a script receives, also listed in the script's form."""
    data = event.data or {}
    return {
        "WIRELOFT_EVENT": event.event,
        "WIRELOFT_TITLE": event.title,
        "WIRELOFT_MESSAGE": event.body or "",
        "WIRELOFT_SHOW": str(data.get("show") or ""),
        "WIRELOFT_EPISODE": str(data.get("episode") or ""),
        "WIRELOFT_FILE_PATH": str(data.get("filePath") or ""),
        "WIRELOFT_FOLDER": str(data.get("folder") or ""),
    }


SCRIPT_VARIABLES = tuple(script_environment(EventRow(event="", title="", data={})).keys())


def run_script(config: dict[str, Any], event: EventRow) -> Outcome:
    try:
        path = script_path(config["script"])
    except InvalidDestination as error:
        return Outcome(False, str(error))
    try:
        result = subprocess.run(
            [str(path)], env={"PATH": "/usr/local/bin:/usr/bin:/bin", **script_environment(event)},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
            timeout=config["timeout_seconds"], cwd=str(path.parent),
        )
    except subprocess.TimeoutExpired:
        return Outcome(False, f"It ran longer than {config['timeout_seconds']} seconds and was stopped")
    except OSError as error:
        return Outcome(False, f"It could not start: {error}"[:ERROR_LIMIT])
    output = result.stdout.strip()
    if output:
        logger.info("Script %s for %s said:\n%s", path.name, event.event, output[-4000:])
    if result.returncode != 0:
        last = output.splitlines()[-1] if output else ""
        return Outcome(False, f"It ended with exit code {result.returncode}{': ' + last if last else ''}"[:ERROR_LIMIT])
    return Outcome(True)


def test_destination(destination_kind: Kind, config: dict[str, Any], sample: EventRow | None) -> Outcome:
    """Try a destination: a test message, a connection check, a sample webhook, or the script on the newest download."""
    if destination_kind == Kind.APPRISE:
        return send_message(
            config, title="WireLoft test message", body="If you can read this, WireLoft can reach this destination.",
            tone=Tone.INFO,
        )
    if destination_kind == Kind.PLEX:
        return _request("GET", f"{config['address']}/library/sections", headers={"X-Plex-Token": config["api_key"]})
    if destination_kind in (Kind.JELLYFIN, Kind.EMBY):
        return _request("GET", f"{config['address']}/System/Info", headers={"X-Emby-Token": config["api_key"]})
    event = sample or EventRow(
        event=Event.EPISODE_DOWNLOADED.value, title="WireLoft test", body="A test from WireLoft", data={},
    )
    if destination_kind == Kind.WEBHOOK:
        return call_webhook(config, {**webhook_payload(event), "test": True})
    return run_script(config, event)


def tone_of(event: str) -> Tone:
    definition = DEFINITIONS.get(Event(event)) if event in Event._value2member_map_ else None
    return definition.tone if definition else Tone.INFO


def destination_kind(destination: NotificationDestination) -> Kind:
    return Kind(destination.kind)
