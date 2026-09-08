from __future__ import annotations

import errno
import socket
from collections.abc import Iterator
from typing import Any


NO_INTERNET_CONNECTION_MESSAGE = "No internet connection"


class NoInternetConnectionError(ConnectionError):
    """Raised when the host clearly has no usable route/DNS path to the internet."""

    def __init__(self) -> None:
        super().__init__(NO_INTERNET_CONNECTION_MESSAGE)


_NETWORK_ERRNOS = {
    value
    for value in (
        getattr(errno, "ENETDOWN", None),
        getattr(errno, "ENETUNREACH", None),
        getattr(errno, "EHOSTDOWN", None),
        getattr(errno, "EHOSTUNREACH", None),
    )
    if value is not None
}

_GAI_ERRNOS = {
    value
    for value in (
        getattr(socket, "EAI_AGAIN", None),
        getattr(socket, "EAI_FAIL", None),
    )
    if value is not None
}

_NETWORK_TEXT_MARKERS = (
    "temporary failure in name resolution",
    "network is unreachable",
    "network unreachable",
    "no route to host",
    "nodename nor servname provided, or not known",
    "getaddrinfo failed",
    "could not resolve host",
    "failed to resolve host",
    "failed to resolve hostname",
)


def _exception_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield nested transport exceptions without relying on one HTTP library."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        yield current

        for nested in (
            current.__cause__,
            current.__context__,
            getattr(current, "reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
        for nested in getattr(current, "exceptions", ()):
            if isinstance(nested, BaseException):
                pending.append(nested)
        for arg in current.args:
            if isinstance(arg, BaseException):
                pending.append(arg)


def message_indicates_no_internet(value: Any) -> bool:
    """Recognize transport messages that specifically indicate local connectivity loss."""
    text = str(value or "").casefold()
    return any(marker in text for marker in _NETWORK_TEXT_MARKERS)


def is_no_internet_error(error: BaseException | None) -> bool:
    """Return True only for strong evidence that the local internet path is unavailable.

    Generic timeouts, TLS failures, connection refusals and HTTP errors are deliberately
    excluded because they can mean that only the remote service is unhealthy.
    """
    if error is None:
        return False

    for current in _exception_chain(error):
        if isinstance(current, NoInternetConnectionError):
            return True
        if isinstance(current, socket.gaierror) and current.errno in _GAI_ERRNOS:
            return True
        if isinstance(current, OSError) and current.errno in _NETWORK_ERRNOS:
            return True
        if message_indicates_no_internet(current):
            return True
    return False


def normalize_no_internet_error(error: BaseException) -> BaseException:
    """Replace a library-specific outage exception with WireLoft's stable error."""
    if isinstance(error, NoInternetConnectionError):
        return error
    if is_no_internet_error(error):
        normalized = NoInternetConnectionError()
        normalized.__cause__ = error
        return normalized
    return error
