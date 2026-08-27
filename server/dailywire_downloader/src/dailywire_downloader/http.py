from __future__ import annotations

import time
from typing import Iterator, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import DownloadError, MediaUnavailableError

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
        return self._raw.read()

    def iter_chunks(self, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
        while True:
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

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = Request(url, headers=request_headers, method="GET")
        try:
            return HttpResponse(urlopen(req, timeout=timeout))
        except HTTPError as e:
            if e.code in _UNAVAILABLE_STATUS_CODES:
                raise MediaUnavailableError(f"HTTP {e.code} for {url}") from e
            last_error = e
            if e.code not in _TRANSIENT_STATUS_CODES:
                break
        except URLError as e:
            last_error = e
        except Exception as e:  # noqa: BLE001 - normalized below
            last_error = e

        if attempt < retries:
            time.sleep(_RETRY_DELAY_S * (attempt + 1))

    raise DownloadError(f"Request failed for {url}: {last_error}") from last_error


def http_get_text(url: str, **kwargs) -> str:
    with http_get(url, **kwargs) as resp:
        return resp.read().decode("utf-8", errors="replace")
