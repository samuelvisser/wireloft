"""Describes the services Apprise can send to and turns form values into Apprise URLs.

Apprise publishes machine-readable details for each service: URL templates, the
tokens that fill them and optional query arguments. The Add channel form is
generated from that catalog, so WireLoft does not need hand-written UI for each
of the 150+ services, and a new Apprise release brings new services for free.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from urllib.parse import quote, quote_plus

from apprise import Apprise, AppriseAsset, PersistentStoreMode

# Services that act on the machine WireLoft runs on rather than reaching a
# network destination, plus Web Push, which WireLoft already handles itself.
UNSUPPORTED_PROTOCOLS = frozenset({
    "dbus", "kde", "qt", "glib", "gnome", "macosx", "windows", "syslog", "vapid",
})

# Query arguments Apprise offers for every service. They tune transport rather
# than describe a destination, so the form leaves them out.
TRANSPORT_ARGUMENTS = frozenset({
    "verify", "redirect", "rto", "cto", "overflow", "format", "emojis", "store",
    "tz", "retry", "wait", "optional", "attach", "filename", "image", "batch",
})

# One Apprise asset for everything WireLoft sends. Messages are never persisted
# to disk by Apprise's own storage; WireLoft keeps its own delivery ledger.
APPRISE_ASSET = AppriseAsset(storage_mode=PersistentStoreMode.MEMORY)

_TOKEN = re.compile(r"\{(\w+)\}")
_SCHEMA = "schema"

FieldValue = str | int | float | bool | list[str]


class FieldKind(StrEnum):
    TEXT = "text"
    SECRET = "secret"
    NUMBER = "number"
    SELECT = "select"
    BOOLEAN = "boolean"
    LIST = "list"


@dataclass(frozen=True)
class FieldChoice:
    value: str
    label: str


@dataclass(frozen=True)
class ServiceField:
    key: str
    label: str
    kind: FieldKind
    required: bool
    advanced: bool
    choices: tuple[FieldChoice, ...] = ()
    default: str | None = None


@dataclass(frozen=True)
class ServiceDefinition:
    key: str
    name: str
    service_url: str | None
    setup_url: str | None
    fields: tuple[ServiceField, ...]
    templates: tuple[str, ...]
    protocols: tuple[str, ...]


class InvalidDestination(ValueError):
    """The submitted values do not describe a destination Apprise can send to."""


def _field_kind(token: Mapping, *, private: bool) -> FieldKind:
    kind = str(token.get("type", "string"))
    if kind.startswith("choice"):
        return FieldKind.SELECT
    if kind.startswith("list"):
        return FieldKind.LIST
    if kind in ("int", "float"):
        return FieldKind.NUMBER
    if kind == "bool":
        return FieldKind.BOOLEAN
    return FieldKind.SECRET if private else FieldKind.TEXT


def _choices(token: Mapping) -> tuple[FieldChoice, ...]:
    values = token.get("values") or ()
    return tuple(FieldChoice(str(v), str(v)) for v in sorted(values, key=str)) if isinstance(values, (set, frozenset)) \
        else tuple(FieldChoice(str(v), str(v)) for v in values)


def _default(token: Mapping) -> str | None:
    default = token.get("default")
    if default is None:
        return None
    return str(getattr(default, "value", default))


def _schema_field(protocols: tuple[str, ...], secure: tuple[str, ...]) -> ServiceField | None:
    if len(protocols) + len(secure) < 2:
        return None
    choices = tuple(FieldChoice(p, f"{p}:// (secure)") for p in secure) \
        + tuple(FieldChoice(p, f"{p}:// (not encrypted)") for p in protocols)
    return ServiceField(
        key=_SCHEMA, label="Connection", kind=FieldKind.SELECT, required=True, advanced=False,
        choices=choices, default=(secure or protocols)[0],
    )


def _definition(entry: Mapping, key: str) -> ServiceDefinition:
    details = entry["details"]
    protocols = tuple(entry.get("protocols") or ())
    secure = tuple(entry.get("secure_protocols") or ())
    templates = tuple(str(t) for t in details["templates"])
    tokens: Mapping[str, Mapping] = details["tokens"]

    template_tokens = [set(_TOKEN.findall(t)) - {_SCHEMA} for t in templates]
    ordered: list[str] = []
    for template in templates:
        for name in _TOKEN.findall(template):
            if name != _SCHEMA and name not in ordered:
                ordered.append(name)

    fields: list[ServiceField] = []
    schema_field = _schema_field(protocols, secure)
    if schema_field is not None:
        fields.append(schema_field)
    for name in ordered:
        token = tokens.get(name)
        if token is None:
            continue
        private = bool(token.get("private"))
        fields.append(ServiceField(
            key=name,
            label=str(token.get("name", name)),
            kind=_field_kind(token, private=private),
            required=all(name in used for used in template_tokens),
            advanced=False,
            choices=_choices(token) if str(token.get("type", "")).startswith("choice") else (),
            default=_default(token),
        ))
    for name, arg in sorted(details["args"].items()):
        if name in TRANSPORT_ARGUMENTS or "alias_of" in arg or name in ordered or name == _SCHEMA:
            continue
        private = bool(arg.get("private"))
        fields.append(ServiceField(
            key=name,
            label=str(arg.get("name", name)),
            kind=_field_kind(arg, private=private),
            required=False,
            advanced=True,
            choices=_choices(arg) if str(arg.get("type", "")).startswith("choice") else (),
            default=_default(arg),
        ))

    return ServiceDefinition(
        key=key,
        name=str(entry["service_name"]),
        service_url=entry.get("service_url"),
        setup_url=entry.get("setup_url"),
        fields=tuple(fields),
        templates=templates,
        protocols=secure + protocols,
    )


@lru_cache(maxsize=1)
def service_catalog() -> tuple[ServiceDefinition, ...]:
    catalog: list[ServiceDefinition] = []
    used_keys: set[str] = set()
    for entry in Apprise(asset=APPRISE_ASSET).details()["schemas"]:
        protocols = tuple(entry.get("protocols") or ()) + tuple(entry.get("secure_protocols") or ())
        if not protocols or UNSUPPORTED_PROTOCOLS.intersection(protocols):
            continue
        key = protocols[0]
        if key in used_keys:
            continue
        used_keys.add(key)
        catalog.append(_definition(entry, key))
    return tuple(sorted(catalog, key=lambda service: service.name.lower()))


@lru_cache(maxsize=1)
def _services_by_key() -> dict[str, ServiceDefinition]:
    return {service.key: service for service in service_catalog()}


@lru_cache(maxsize=1)
def _services_by_protocol() -> dict[str, ServiceDefinition]:
    return {protocol: service for service in service_catalog() for protocol in service.protocols}


def service_display_name(key: str) -> str:
    service = _services_by_key().get(key)
    return service.name if service is not None else key


def service_for_key(key: str) -> ServiceDefinition:
    try:
        return _services_by_key()[key]
    except KeyError:
        raise InvalidDestination("Choose a supported notification service") from None


def _is_filled(value: FieldValue | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, list):
        return any(item.strip() for item in value)
    return True


def _encode(value: FieldValue) -> str:
    if isinstance(value, list):
        return "/".join(quote(item.strip(), safe="") for item in value if item.strip())
    return quote(str(value).strip(), safe="")


def _query_value(value: FieldValue) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ",".join(item.strip() for item in value if item.strip())
    return str(value).strip()


def build_url(service_key: str, values: Mapping[str, FieldValue]) -> str:
    """Fill the Apprise URL template that exactly matches the fields the user completed."""
    service = service_for_key(service_key)
    fields = {field.key: field for field in service.fields}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise InvalidDestination(f"{service.name} does not use: {', '.join(unknown)}")

    filled = {key: value for key, value in values.items() if _is_filled(value) and key != _SCHEMA}
    token_values = {key: value for key, value in filled.items() if not fields[key].advanced}
    schema_field = fields.get(_SCHEMA)
    schema = str(values.get(_SCHEMA) or (schema_field.default if schema_field else service.protocols[0]))
    if schema not in service.protocols:
        raise InvalidDestination(f"{schema}:// is not a connection type for {service.name}")

    match = next((
        template for template in service.templates
        if set(_TOKEN.findall(template)) - {_SCHEMA} == set(token_values)
    ), None)
    if match is None:
        raise InvalidDestination(_missing_message(service, set(token_values)))

    url = _TOKEN.sub(
        lambda found: schema if found.group(1) == _SCHEMA else _encode(token_values[found.group(1)]),
        match,
    )
    query = "&".join(
        f"{quote_plus(key)}={quote_plus(_query_value(value))}"
        for key, value in filled.items() if fields[key].advanced
    )
    return f"{url}?{query}" if query else url


def _missing_message(service: ServiceDefinition, given: set[str]) -> str:
    labels = {field.key: field.label for field in service.fields}
    options = [
        " + ".join(labels.get(name, name) for name in _TOKEN.findall(template) if name != _SCHEMA)
        for template in service.templates
    ]
    shown = "; or ".join(dict.fromkeys(option for option in options if option))
    return f"{service.name} needs one of these combinations of fields: {shown}"


def parse_destination(url: str):
    """Return the Apprise plugin for a URL, or reject it as not sendable."""
    candidate = url.strip()
    if "://" not in candidate:
        raise InvalidDestination("An Apprise URL looks like service://credentials")
    scheme = candidate.split("://", 1)[0].lower()
    if scheme in UNSUPPORTED_PROTOCOLS:
        raise InvalidDestination(f"{scheme}:// is not supported by WireLoft")
    plugin = Apprise.instantiate(candidate, asset=APPRISE_ASSET)
    if plugin is None:
        raise InvalidDestination("Apprise could not use these settings. Check the details and try again.")
    return plugin


def service_key_for_url(url: str) -> str:
    scheme = url.strip().split("://", 1)[0].lower()
    service = _services_by_protocol().get(scheme)
    return service.key if service is not None else scheme


def masked_url(url: str) -> str:
    """A version of the URL that is safe to show: Apprise hides secrets, then drop the options."""
    return parse_destination(url).url(privacy=True).split("?", 1)[0]
