from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import MIDDLEWARE_API


class MiddlewareAPIError(Exception):
    """Errors raised while communicating with DailyWire Middleware API."""


class MiddlewareClient:
    """
    Minimal HTTP client for DailyWire Middleware API.

    Endpoints (based on provided C# reference):
      - GET v3/getUserInfo?nocache={0|1}
      - GET v4/getPage?slug=...&membershipPlan=...
      - GET v4/getShowPage?slug=...&membershipPlan=...
      - GET v4/getEpisode?slug=...

    Pass an access token if you have one; premium content typically requires it.
    """

    def __init__(self, access_token: Optional[str] = None, timeout: float = 30.0, base_url: str = MIDDLEWARE_API) -> None:
        self._timeout = timeout
        self._base_url = base_url.rstrip('/')
        headers = {
            # These are generally not required for Middleware, but harmless if present
            'Accept': 'application/json',
            'User-Agent': 'wireloft/0.2 (+https://www.dailywire.com)'
        }
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        self._headers = headers

    # --------------- public methods ---------------
    def get_user_info(self, no_cache: bool = True) -> Dict[str, Any]:
        return self._get('v3/getUserInfo', {'nocache': 1 if no_cache else 0})

    def get_page(self, slug: str, membership_plan: Optional[str] = None, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {'slug': slug}
        if membership_plan:
            params['membershipPlan'] = membership_plan
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        return self._get('v4/getPage', params)

    def get_show_page(self, slug: str, membership_plan: Optional[str] = None, extra_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {'slug': slug}
        if membership_plan:
            params['membershipPlan'] = membership_plan
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        return self._get('v4/getShowPage', params)

    def get_episode(self, slug: str) -> Dict[str, Any]:
        return self._get('v4/getEpisode', {'slug': slug})

    # --------------- internals ---------------
    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        qs = urlencode(params or {})
        url = f"{self._base_url}/{endpoint}"
        if qs:
            url = f"{url}?{qs}"
        req = Request(url, headers=self._headers, method='GET')
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                data = resp.read()
        except HTTPError as e:
            try:
                err_body = e.read().decode('utf-8', errors='ignore')
            except Exception:
                err_body = ''
            raise MiddlewareAPIError(f"HTTP error {e.code}: {err_body or e.reason}") from e
        except URLError as e:
            raise MiddlewareAPIError(f"Network error: {e.reason}") from e
        except Exception as e:
            raise MiddlewareAPIError(str(e)) from e

        try:
            parsed = json.loads(data.decode('utf-8'))
        except Exception as e:
            raise MiddlewareAPIError('Failed to parse JSON response') from e

        if not isinstance(parsed, dict):
            return {}
        # Middleware tends to return an 'error' string or code fields on failure; pass-through
        return parsed
