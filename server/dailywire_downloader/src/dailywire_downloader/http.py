from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from typing import Iterator, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import DownloadCancelled, DownloadError, MediaUnavailableError
from .transfer_context import TransferWait, cancel_check, wait_observer

USER_AGENT = "wireloft-downloader/1.0"

# Status codes that mean "this URL will not start working by itself":
# the caller should obtain a fresh URL instead of retrying.
_UNAVAILABLE_STATUS_CODES = {400, 401, 403, 404, 410}
# Status codes worth retrying with a short backoff.
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_RETRIES = 3
_RETRY_DELAY_S = 1.5


class HttpResponse:
    """Thin wrapper so callers don't deal with urllib response objects."""

    def __init__(self, raw):
        self._raw = raw
        self.status: int = raw.status
        self.headers: Mapping[str, str] = raw.headers

    def read(self) -> bytes:
        _check_cancelled()
        result = self._raw.read()
        _check_cancelled()
        return result

    def iter_chunks(self, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
        while True:
            _check_cancelled()
            chunk = self._raw.read(chunk_size)
            if not chunk:
                return
            yield chunk

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> "HttpResponse":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def _encode_raw_spaces(url: str) -> str:
    """Make a URL request-safe without changing existing percent encoding."""
    return url.replace(" ", "%20")


def http_get(
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        timeout: float = _DEFAULT_TIMEOUT,
        retries: int = _DEFAULT_RETRIES,
) -> HttpResponse:
    """GET a URL, retrying transient failures.

    Raises MediaUnavailableError for permanent failures (expired/invalid URLs)
    and DownloadError for anything else that keeps failing.
    """
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    request_url = _encode_raw_spaces(url)

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        _check_cancelled()
        req = Request(request_url, headers=request_headers, method="GET")
        try:
            return HttpResponse(urlopen(req, timeout=timeout))
        except HTTPError as e:
            if e.code in _UNAVAILABLE_STATUS_CODES:
                raise MediaUnavailableError(f"HTTP {e.code} for {_safe_url(url)}") from e
            last_error = e
            if e.code not in _TRANSIENT_STATUS_CODES:
                break
        except DownloadCancelled:
            raise
        except URLError as e:
            last_error = e
        except Exception as e:  # noqa: BLE001 - normalized below
            last_error = e

        if attempt < retries:
            wait_for_retry(last_error, attempt)

    raise DownloadError(f"Request failed for {_safe_url(url)}: {type(last_error).__name__}") from last_error


def http_get_text(url: str, **kwargs) -> str:
    with http_get(url, **kwargs) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))


def _check_cancelled() -> None:
    check = cancel_check.get()
    if check is not None and check():
        raise DownloadCancelled("Download was canceled")


def retry_delay(error: BaseException | None, attempt: int) -> tuple[float, str]:
    """Respect upstream Retry-After; do not mistake it for our own API pacing."""
    cause = error
    while cause is not None:
        headers = getattr(cause, "headers", None)
        value = headers.get("Retry-After") if headers is not None else None
        if value is not None:
            try:
                return max(0.0, float(value)), "upstream_retry"
            except ValueError:
                try:
                    deadline = parsedate_to_datetime(value)
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    return max(0.0, deadline.timestamp() - time.time()), "upstream_retry"
                except (TypeError, ValueError, OverflowError):
                    pass
        cause = cause.__cause__
    return _RETRY_DELAY_S * (attempt + 1), "retry_backoff"


def wait_for_retry(error: BaseException | None, attempt: int) -> None:
    delay, reason = retry_delay(error, attempt)
    observer = wait_observer.get()
    deadline = time.monotonic() + delay
    if observer is not None:
        observer(TransferWait(reason, time.time() + delay))
    try:
        while True:
            _check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
    finally:
        if observer is not None:
            observer(None)
