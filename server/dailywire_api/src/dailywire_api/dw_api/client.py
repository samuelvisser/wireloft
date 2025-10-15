import json

from builtins import str
from dataclasses import dataclass
from typing import Dict, ClassVar, Any, Optional, Literal, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen

from pydantic import ValidationError

from dailywire_api.records.ShowRecord import ShowRecord
from dailywire_api.records.EpisodeRecord import EpisodeRecord
from wireloft_config import get_settings


@dataclass(frozen=True)
class ByNextPage:
    next_page_url: str


@dataclass(frozen=True, kw_only=True)
class _ByParameters:
    membership_plan: Optional[str] = None
    page_size: int = 20
    page_number: int = 1
    order_by: str = "CreatedAt_DESC"
    show_offset: Optional[int] = None
    podcast_offset: Optional[int] = None


@dataclass(frozen=True)
class _BySeason(_ByParameters):
    season_id: str
    param_key: ClassVar[Literal["showSeasonId", "podcastSeasonId"]]


@dataclass(frozen=True)
class ByShowSeason(_BySeason):
    param_key: ClassVar[str] = "showSeasonId"


@dataclass(frozen=True)
class ByPodcastSeason(_BySeason):
    param_key: ClassVar[str] = "podcastSeasonId"

class EpisodesPaginatedResult(NamedTuple):
    items: list[Dict[str, Any]]
    next_page_url: Optional[str]
    has_next: bool


class MiddlewareAPIError(Exception):
    """Errors raised while communicating with DailyWire Middleware API."""


class MiddlewareClient:
    """
    HTTP client for DailyWire Middleware API.

    Pass an access token if you have one; premium content typically requires it.
    """

    def __init__(self, access_token: Optional[str] = None, timeout: float = 30.0, base_url: str = get_settings().dw_api.middleware_api) -> None:
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
    def get_show_page(self, slug: str, membership_plan: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {'slug': slug}
        if membership_plan:
            params['membershipPlan'] = membership_plan

        payload = self._get('v4/getShowPage', params)
        record = ShowRecord.model_validate(payload)

        return record.model_dump(by_alias=True, mode="json")

    def get_episodes_paginated(self, slug: str, selector: ByNextPage | ByShowSeason | ByPodcastSeason) -> EpisodesPaginatedResult:
        """
        Fetch a single page of episodes for a show.

        You can either:
          - continue from a previous response by providing next_page_url, OR
          - start a new query by providing the standard params (slug, membership_plan, etc.)
            AND one of show_season_id or podcast_season_id (required union).

        Returns a dict with:
          - items: list[dict] EpisodeRecord dicts (JSON-friendly)
          - next_page_url: str | None
          - has_next: bool
          - raw: raw page payload (as dict)
        """
        endpoint = 'v4/getPaginatedEpisodes'
        params: Dict[str, Any] = {}

        match selector:
            case ByNextPage(next_page_url):
                parsed = urlparse(next_page_url)
                q = parsed.query
                path = parsed.path or ''
                if path:
                    path = path.lstrip('/')
                    if path.startswith('middleware/'):
                        path = path[len('middleware/'):]
                    # If path mentions the endpoint, use it; otherwise assume default endpoint
                    if path:
                        endpoint = path
                if q:
                    qs = parse_qs(q)
                    for k, v in qs.items():
                        if not v:
                            continue
                        params[k] = v[0] if len(v) == 1 else v


            case _BySeason(season_id=sid) as sel:
                params = {
                    "slug": slug,
                    "orderBy": sel.order_by,
                    "pageNumber": sel.page_number,
                    "pageSize": sel.page_size,
                    "showOffset": 0 if sel.show_offset is None else sel.show_offset,
                    "podcastOffset": 0 if sel.podcast_offset is None else sel.podcast_offset,
                    type(sel).param_key: sid,    # use the subclass’ key
                }
                if sel.membership_plan:
                    params["membershipPlan"] = sel.membership_plan

        try:
            payload = self._get(endpoint, params)
        except MiddlewareAPIError as e:
            # Usually thrown when there are no more episodes in the current season
            return EpisodesPaginatedResult([], None, False)

        # Extract items
        items_raw = payload.get('componentItems')

        # Normalize to EpisodeRecord dicts
        episodes: list[dict] = []
        for it in items_raw or []:
            try:
                ep = EpisodeRecord.model_validate(it).model_dump(by_alias=True, mode='json')
                episodes.append(ep)
            except ValidationError:
                # Skip items that fail validation; continue best-effort
                continue

        next_url = payload.get('nextPageUrl') or payload.get('nextPageURL') or None

        return EpisodesPaginatedResult(
            items=episodes,
            next_page_url=next_url,
            has_next=bool(next_url)
        )

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
