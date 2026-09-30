import json
import logging
import time

from builtins import str
from dataclasses import dataclass
from typing import Callable, Dict, ClassVar, Any, Iterator, Optional, Literal, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from pydantic import ValidationError

from dailywire_api.records import (
    DwCatalogMovieRecord,
    DwCatalogRecord,
    DwCatalogShowRecord,
    DwEpisodeDetailRecord,
    DwEpisodeRecord,
    DwMovieExtraDetailRecord,
    DwMovieDetailRecord,
    DwShowRecord,
    DwUserInfo,
)
from dailywire_authorisation import DeviceAuthClient
from config import get_settings

logger = logging.getLogger(__name__)

from dailywire_api.pacing import (
    RequestCancelled, RequestPriority, check_cancelled,
    wait_before_request, wait_for_retry,
)


@dataclass(frozen=True)
class ByNextPage:
    next_page_url: str


@dataclass(frozen=True, kw_only=True)
class _ByParameters:
    membership_plan: Optional[str] = None
    order_by: str = "CreatedAt_DESC"
    page_number: int = 1
    page_size: int = 20
    show_offset: int = 0
    podcast_offset: int = 0


@dataclass(frozen=True)
class _BySeason(_ByParameters):
    season_dw_id: str
    season_id_key: ClassVar[Literal["showSeasonId", "podcastSeasonId"]]


@dataclass(frozen=True)
class ByShowSeason(_BySeason):
    season_id_key: ClassVar[str] = "showSeasonId"


@dataclass(frozen=True)
class ByPodcastSeason(_BySeason):
    season_id_key: ClassVar[str] = "podcastSeasonId"


class EpisodesPaginatedResult(NamedTuple):
    items: list[DwEpisodeRecord]
    next_page_url: Optional[str]
    has_next: bool


class MiddlewareAPIError(Exception):
    """Errors raised while communicating with DailyWire Middleware API."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MiddlewareClient:
    """
    HTTP client for DailyWire Middleware API.

    Pass an access token if you have one; premium content typically requires it.
    Bulk/background requests share global pacing. Interactive reads preserve
    WireLoft's explicit pacing override: they bypass the wait but still count
    toward the burst/cooldown accounting seen by background work.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        request_timeout: float = 30.0,
        base_url: str = get_settings().dw_api.middleware_api,
        request_priority: RequestPriority | None = None,
        pace_requests: bool | None = None,
    ) -> None:
        self._req_timeout = request_timeout
        self._base_url = base_url.rstrip('/')
        # Preserve the pre-planner explicit bypass while also supporting the
        # newer execution-scoped priority model. False is intentionally stronger
        # than a supplied priority: it means this client must never wait for
        # global pacing.
        self._request_priority = (
            "interactive"
            if pace_requests is False
            else request_priority
        )
        headers = {
            # These are generally not required for Middleware, but harmless if present
            'Accept': 'application/json',
            'User-Agent': 'wireloft/0.2 (+https://www.dailywire.com)'
        }
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        self._headers = headers

    # --------------- public methods ---------------
    def get_show_page(self, slug: str, *, membership_plan: Optional[str] = None) -> DwShowRecord:
        params: Dict[str, Any] = {'slug': slug}
        if membership_plan:
            params['membershipPlan'] = membership_plan

        payload = self._get('v4/getShowPage', params)
        return DwShowRecord.model_validate(payload)

    def get_catalog(self, *, membership_plan: Optional[str] = None) -> DwCatalogRecord:
        """Return the shows and movies exposed by Daily Wire's browse page.

        The upstream response repeats items across curated carousels. WireLoft
        deliberately flattens and de-duplicates those rows so the frontend can
        offer stable alphabetical and host-grouped browsing.
        """
        params: Dict[str, Any] = {'slug': 'web-shows-movies-page'}
        if membership_plan:
            params['membershipPlan'] = membership_plan
        payload = self._get('v4/getPage', params)

        shows: dict[str, DwCatalogShowRecord] = {}
        movies: dict[str, DwCatalogMovieRecord] = {}
        for component in payload.get('components') or []:
            for item in component.get('items') or []:
                raw_show = item.get('show')
                if isinstance(raw_show, dict) and raw_show.get('slug'):
                    record = self._catalog_show_from_payload(raw_show)
                    shows.setdefault(record.slug, record)

                raw_movie = item.get('video')
                if isinstance(raw_movie, dict) and raw_movie.get('slug'):
                    record = DwCatalogMovieRecord.model_validate(raw_movie)
                    movies.setdefault(record.slug, record)

        return DwCatalogRecord(
            shows=sorted(shows.values(), key=lambda value: value.title.casefold()),
            movies=sorted(movies.values(), key=lambda value: value.title.casefold()),
        )

    def get_square_show_thumbnails(
        self,
        *,
        membership_plan: Optional[str] = None,
    ) -> dict[str, str]:
        """Return square show artwork exposed by the Watch page carousel.

        The Daily Wire currently leaves images.thumbnail.square empty in this
        component and currently duplicates the square artwork into both the
        land and port fields. WireLoft only interprets that duplicate pair as
        square art when those two URLs are exactly equal, so genuinely distinct
        future orientations are not mislabeled.
        """
        params: Dict[str, Any] = {'slug': 'watch-page'}
        if membership_plan:
            params['membershipPlan'] = membership_plan
        payload = self._get('v4/getPage', params)

        thumbnails: dict[str, str] = {}
        for component in payload.get('components') or []:
            if (
                not isinstance(component, dict)
                or component.get('renderType') != 'squareShowCarousel'
            ):
                continue

            for item in component.get('items') or []:
                if not isinstance(item, dict):
                    continue
                raw_show = item.get('show')
                if not isinstance(raw_show, dict):
                    continue

                record = self._catalog_show_from_payload(raw_show)
                square_path = record.thumbnail_square_path
                if square_path is None:
                    raw_thumbnails = (raw_show.get('images') or {}).get('thumbnail') or {}
                    raw_landscape = raw_thumbnails.get('land')
                    raw_portrait = raw_thumbnails.get('port')
                    if (
                        isinstance(raw_landscape, str)
                        and raw_landscape
                        and raw_landscape == raw_portrait
                    ):
                        square_path = raw_landscape

                if not record.slug or not square_path:
                    continue
                thumbnails.setdefault(record.slug, square_path)

        return thumbnails

    def get_movie_playback(self, slug: str) -> DwMovieDetailRecord:
        """Fetch Daily Wire's current signed movie playback URL.

        Movie metadata is resolved through ``v4/getMoviePage`` by
        ``MovieMiddlewareClient``. Daily Wire's own current web player still uses
        ``v2/getVideo`` to obtain the signed movie stream, so playback intentionally
        remains on this endpoint.
        """
        payload = self._get('v2/getVideo', {'slug': slug})
        raw = payload.get('video')
        if not isinstance(raw, dict):
            message = payload.get('error') or payload.get('message') or 'Movie playback is unavailable'
            raise MiddlewareAPIError(str(message))

        secure_video_url = raw.get('secureVideoURL') or None
        video_url = (
            self._resolve_secure_video_url(secure_video_url)
            if secure_video_url
            else raw.get('videoURL') or None
        )
        return DwMovieDetailRecord(
            video_url=video_url,
            trailer_url=raw.get('trailerURL') or None,
            duration=float(raw.get('duration') or 0),
            trailer_duration=float(raw.get('trailerDuration') or 0),
            has_video=bool(raw.get('hasVideo')),
        )

    def get_movie_extra_playback(self, slug: str) -> DwMovieExtraDetailRecord:
        """Fetch playback and authoritative clip metadata for a movie extra.

        Daily Wire represents movie extras as ``showEpisode`` rows on the movie
        page, but their playback endpoint is ``getClip``. The movie-only
        ``getVideo`` endpoint returns ``404 video not found`` for these slugs.
        """
        payload = self._get('v4/getClip', {'slug': slug})
        raw = payload.get('clip') if isinstance(payload.get('clip'), dict) else payload
        if not isinstance(raw, dict) or not raw.get('slug'):
            message = payload.get('error') or payload.get('message') or 'Movie-extra playback is unavailable'
            raise MiddlewareAPIError(str(message))

        secure_video_url = raw.get('secureVideoURL') or None
        video_url = (
            self._resolve_secure_video_url(secure_video_url)
            if secure_video_url
            else raw.get('videoURL') or None
        )
        if not video_url:
            mux_playback_id = str(raw.get('muxPlaybackId') or '').strip()
            mux_playback_token = str(raw.get('muxPlaybackToken') or '').strip()
            playback_policy = str(raw.get('playbackPolicy') or '').strip().casefold()
            if mux_playback_id and (mux_playback_token or playback_policy == 'public'):
                video_url = f"https://stream.mux.com/{quote(mux_playback_id, safe='')}.m3u8"
                if mux_playback_token:
                    video_url = f"{video_url}?{urlencode({'token': mux_playback_token})}"

        return DwMovieExtraDetailRecord.from_clip_payload(
            raw,
            video_url=video_url,
        )

    def _resolve_secure_video_url(self, secure_url: str) -> str:
        """Exchange Daily Wire's authenticated resolver URL for its CDN URL."""
        if not self._is_middleware_url(secure_url):
            return self._validated_playback_url(secure_url)

        payload = self._get_url(secure_url)
        destination = payload.get('destination')
        if not isinstance(destination, str) or not destination:
            raise MiddlewareAPIError('Daily Wire returned no movie playback destination')
        return self._validated_playback_url(destination)

    def _is_middleware_url(self, url: str) -> bool:
        candidate = urlparse(url)
        middleware = urlparse(self._base_url)
        return (
            candidate.scheme in {'http', 'https'}
            and candidate.scheme == middleware.scheme
            and candidate.netloc == middleware.netloc
        )

    @staticmethod
    def _validated_playback_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise MiddlewareAPIError('Daily Wire returned an invalid movie playback URL')
        return url

    def get_user_info(self) -> DwUserInfo:
        """
        Fetch the current user's info using DailyWire Middleware API.
        Access token is obtained from dailywire_authorisation package.
        """
        tokens = DeviceAuthClient().get_token()
        if not tokens:
            raise MiddlewareAPIError("No valid access token in token store")
        access_token = tokens.access_token

        # Temporarily set Authorization header, preserving any existing value
        headers_backup = self._headers.copy()
        try:
            self._headers['Authorization'] = f'Bearer {access_token}'
            payload = self._get('v3/getUserInfo', {'nocache': 1})
        finally:
            self._headers = headers_backup

        try:
            record = DwUserInfo.model_validate(payload)
        except ValidationError as e:
            raise MiddlewareAPIError("Invalid user info response") from e

        return record

    def get_episodes_paginated(self, show_slug: str, selector: ByNextPage | ByShowSeason | ByPodcastSeason) -> EpisodesPaginatedResult:
        """
        Fetch a single page of episodes for a show.

        WARNING: unfortunately, when using the "next page" selector, the DW API might return episodes it already did previously.
        You will need to de-duplicate the results yourself.

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

            case _BySeason(season_dw_id=sid) as sel:
                params = {
                    "slug": show_slug,
                    "orderBy": sel.order_by,
                    "pageNumber": sel.page_number,
                    "pageSize": sel.page_size,
                    "showOffset": sel.show_offset,
                    "podcastOffset": sel.podcast_offset,
                    type(sel).season_id_key: sid,
                }
                if sel.membership_plan:
                    params["membershipPlan"] = sel.membership_plan

        try:
            payload = self._get(endpoint, params)
        except MiddlewareAPIError:
            # A season without (further) episodes tends to answer with an error rather
            # than an empty page, so a failing *initial* season request means "no
            # episodes". A failing continuation request however would silently truncate
            # the season, so those are propagated to the caller.
            if isinstance(selector, ByNextPage):
                raise
            return EpisodesPaginatedResult([], None, False)

        # Extract items
        items_raw = payload.get('componentItems')

        # Normalize to EpisodeRecord dicts
        episodes: list[DwEpisodeRecord] = []
        for it in items_raw or []:
            try:
                ep = DwEpisodeRecord.model_validate(it)
                episodes.append(ep)
            except ValidationError as e:
                raise MiddlewareAPIError("Could not validate episode record") from e

        # Prepare next page URL
        next_url = payload.get('nextPageUrl') or payload.get('nextPageURL') or None

        # Return
        return EpisodesPaginatedResult(
            items=episodes,
            next_page_url=next_url,
            has_next=bool(next_url)
        )

    def get_episode_details(self, episode_slug: str, *, require_member_exclusive: bool = False) -> DwEpisodeDetailRecord:
        endpoint = 'v4/getEpisode'
        params: Dict[str, Any] = {
            'slug': episode_slug,
            'nocache': 1,
        }

        if require_member_exclusive:
            tokens = DeviceAuthClient().get_token()
            if not tokens:
                raise MiddlewareAPIError("No valid access token in token store")
            access_token = tokens.access_token

            # Temporarily set Authorization header, preserving any existing value
            headers_backup = self._headers.copy()
            try:
                self._headers['Authorization'] = f'Bearer {access_token}'
                payload = self._get(endpoint, params)
            finally:
                self._headers = headers_backup
        else:
            payload = self._get(endpoint, params)

        try:
            record = DwEpisodeDetailRecord.model_validate(payload)
        except ValidationError as e:
            raise MiddlewareAPIError("Invalid episode detail response") from e

        return record

    def get_show_id_by_slug(self, show_slug: str) -> str:
        dw_show = self.get_show_page(show_slug)
        return dw_show.dw_id

    def get_season_id_by_slugs(self, show_slug: str, season_slug: str) -> str:
        dw_show = self.get_show_page(show_slug)
        dw_season = next((s for s in dw_show.seasons if s.slug == season_slug), None)
        if dw_season is None:
            raise ValueError(f"Season '{season_slug}' not found in DW API for show '{show_slug}'")
        return dw_season.dw_id

    @staticmethod
    def _catalog_show_from_payload(raw: dict[str, Any]) -> DwCatalogShowRecord:
        host = raw.get('host') or raw.get('author') or {}
        images = raw.get('images') or {}
        thumbnails = images.get('thumbnail') or {}
        return DwCatalogShowRecord(
            dw_id=str(raw.get('id') or ''),
            slug=str(raw.get('slug') or ''),
            title=str(raw.get('title') or ''),
            description=raw.get('description') or None,
            author_name=host.get('name') or None,
            author_slug=host.get('slug') or None,
            author_headshot_path=host.get('imageUrl') or host.get('headshot') or None,
            background_image_path=raw.get('backgroundImage') or None,
            logo_image_path=raw.get('logoImage') or None,
            thumbnail_landscape_path=thumbnails.get('land') or None,
            thumbnail_portrait_path=thumbnails.get('port') or None,
            thumbnail_square_path=thumbnails.get('square') or None,
        )

    # --------------- internals ---------------
    _TRANSIENT_HTTP_CODES = (429, 502, 503, 504)
    _TRANSIENT_RETRIES = 2
    _TRANSIENT_RETRY_DELAY_S = 2.0

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        qs = urlencode(params or {})
        url = f"{self._base_url}/{endpoint}"
        if qs:
            url = f"{url}?{qs}"

        return self._get_url(url)

    def _get_url(self, url: str) -> Dict[str, Any]:
        data: Optional[bytes] = None
        for attempt in range(self._TRANSIENT_RETRIES + 1):
            wait_before_request(self._request_priority)

            req = Request(url, headers=self._headers, method='GET')
            try:
                with urlopen(req, timeout=self._req_timeout) as resp:
                    data = resp.read()
                check_cancelled()
                break
            except HTTPError as e:
                try:
                    err_body = e.read().decode('utf-8', errors='ignore')
                except Exception:
                    err_body = ''
                if e.code in self._TRANSIENT_HTTP_CODES and attempt < self._TRANSIENT_RETRIES:
                    wait_for_retry(e, attempt, base_delay=self._TRANSIENT_RETRY_DELAY_S)
                    continue
                raise MiddlewareAPIError(f"HTTP error {e.code}: {err_body or e.reason}", status_code=e.code) from e
            except URLError as e:
                if attempt < self._TRANSIENT_RETRIES:
                    wait_for_retry(e, attempt, base_delay=self._TRANSIENT_RETRY_DELAY_S)
                    continue
                raise MiddlewareAPIError(f"Network error: {e.reason}") from e
            except RequestCancelled:
                raise
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
