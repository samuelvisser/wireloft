import json
import time
from threading import Condition

from builtins import str
from dataclasses import dataclass
from typing import Dict, ClassVar, Any, Optional, Literal, NamedTuple
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
    DwMoviePlaybackRecord,
    DwMovieRecord,
    DwShowRecord,
    DwMovieExtraRecord,
    DwUserInfo,
)
from dailywire_authorisation import DeviceAuthClient
from config import get_settings

# ---------------- request pacing (global across dailywire_api) ----------------
# We intentionally keep this module-level so that all clients share the same pacing state.
# A ticketed Condition serializes request starts without holding the underlying lock while
# a caller waits for its pacing delay. This prevents queued requests from calculating
# delays from stale pre-lock timestamps.
_pacing_condition = Condition()
_pacing_next_ticket: int = 0
_pacing_serving_ticket: int = 0
_last_request_ns: Optional[int] = None
_ms_since_last_request: Optional[int] = None
_fast_requests: int = 0


def _wait_before_request() -> None:
    """Enforce the global Daily Wire request pacing policy.

    Requests take a ticket so their starts remain serialized, but ``Condition.wait``
    releases the pacing lock while a request is delayed. Timing is sampled only after
    a caller reaches the front of the queue, so time spent waiting behind another
    caller can never turn into a negative/stale elapsed interval.

    A request that exceeds ``max_fast_requests`` waits for the configured slow gap and
    then starts a fresh burst. Resetting the burst counter at that point is important:
    otherwise every request already queued behind the cooldown would independently
    incur another full slow delay.
    """
    global _pacing_next_ticket, _pacing_serving_ticket
    global _last_request_ns, _ms_since_last_request, _fast_requests

    st = get_settings().dw_timeout
    min_fast_ms = int(st.min_fast_request_ms)
    min_slow_ms = int(st.min_slow_request_ms)
    max_fast = int(st.max_fast_requests)

    with _pacing_condition:
        ticket = _pacing_next_ticket
        _pacing_next_ticket += 1

        while ticket != _pacing_serving_ticket:
            _pacing_condition.wait()

        try:
            # Sample the clock only after this request owns the pacing turn. A
            # timestamp captured before waiting in the queue can be minutes stale.
            now_ns = time.monotonic_ns()
            if _last_request_ns is None:
                elapsed_ms: Optional[int] = None
                next_fast_requests = 0
                slow_cooldown = False
                target_start_ns = now_ns
            else:
                elapsed_ns = max(0, now_ns - _last_request_ns)
                elapsed_ms = int(elapsed_ns / 1_000_000)

                if elapsed_ms >= min_slow_ms:
                    next_fast_requests = 0
                else:
                    next_fast_requests = _fast_requests + 1

                slow_cooldown = next_fast_requests > max_fast
                target_ms = min_fast_ms
                if slow_cooldown:
                    target_ms = max(target_ms, min_slow_ms)

                target_start_ns = max(
                    now_ns,
                    _last_request_ns + (target_ms * 1_000_000),
                )

            _ms_since_last_request = elapsed_ms

            # Condition.wait() releases the underlying lock. Other callers can
            # therefore enqueue while this request is pacing, but cannot overtake
            # it because only the serving ticket may proceed.
            while True:
                remaining_ns = target_start_ns - time.monotonic_ns()
                if remaining_ns <= 0:
                    break
                _pacing_condition.wait(timeout=remaining_ns / 1_000_000_000)

            _last_request_ns = time.monotonic_ns()
            _fast_requests = 0 if slow_cooldown else next_fast_requests
        finally:
            _pacing_serving_ticket += 1
            _pacing_condition.notify_all()


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
    Request pacing is enabled by default. Low-volume interactive UI reads may
    explicitly disable it so they are not blocked behind background cooldowns.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        request_timeout: float = 30.0,
        base_url: str = get_settings().dw_api.middleware_api,
        pace_requests: bool = True,
    ) -> None:
        self._req_timeout = request_timeout
        self._base_url = base_url.rstrip('/')
        self._pace_requests = bool(pace_requests)
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

    def get_movie_page(self, slug: str, *, membership_plan: Optional[str] = None) -> DwMovieRecord:
        params: Dict[str, Any] = {'slug': slug}
        if membership_plan:
            params['membershipPlan'] = membership_plan
        payload = self._get('v4/getVideoPage', params)
        raw = payload.get('video')
        if not isinstance(raw, dict) or not raw.get('slug'):
            raise MiddlewareAPIError(f"Daily Wire movie '{slug}' was not found")

        extras_by_key: dict[str, DwMovieExtraRecord] = {}
        for tab in payload.get('tabs') or []:
            for component in tab.get('components') or []:
                for item in component.get('items') or []:
                    extra = item.get('showEpisode')
                    if not isinstance(extra, dict) or not extra.get('slug'):
                        continue
                    title = str(extra.get('title') or '')
                    images = extra.get('images') or {}
                    thumbnails = images.get('thumbnail') or {}
                    record = DwMovieExtraRecord(
                        dw_id=str(extra['id']) if extra.get('id') else None,
                        slug=str(extra.get('slug') or ''),
                        title=title,
                        movie_extra_type=self._movie_extra_type(extra),
                        description=extra.get('description') or None,
                        sharing_url=extra.get('sharingURL') or None,
                        published_date=extra.get('publishedAt') or None,
                        duration=float(extra.get('duration') or 0),
                        background_image_path=extra.get('backgroundImage') or None,
                        thumbnail_landscape_path=thumbnails.get('land') or None,
                        thumbnail_portrait_path=thumbnails.get('port') or None,
                        thumbnail_square_path=thumbnails.get('square') or None,
                    )
                    key = record.dw_id or record.slug
                    extras_by_key.setdefault(key, record)

        movie_extras = list(extras_by_key.values())
        trailer_candidates = [
            extra for extra in movie_extras if extra.movie_extra_type == 'trailer'
        ]
        trailer = next(
            (
                extra
                for extra in trailer_candidates
                if 'official trailer' in extra.title.casefold()
            ),
            trailer_candidates[0] if trailer_candidates else None,
        )

        return DwMovieRecord.model_validate({
            **raw,
            'sharingURL': str(raw.get('sharingURL') or f"https://www.dailywire.com/videos/{slug}"),
            'movie_extras': movie_extras,
            'trailer': trailer,
        })

    def get_movie_playback(self, slug: str) -> DwMoviePlaybackRecord:
        """Fetch a fresh, signed playback URL for a movie download."""
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
        return DwMoviePlaybackRecord(
            video_url=video_url,
            trailer_url=raw.get('trailerURL') or None,
            duration=float(raw.get('duration') or 0),
            trailer_duration=float(raw.get('trailerDuration') or 0),
            has_video=bool(raw.get('hasVideo')),
        )

    def get_movie_extra_playback(self, slug: str) -> DwMoviePlaybackRecord:
        """Fetch a fresh playback URL for a clip listed as a movie extra.

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

        return DwMoviePlaybackRecord(
            video_url=video_url,
            trailer_url=None,
            duration=float(raw.get('duration') or 0),
            trailer_duration=0,
            has_video=bool(video_url),
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
                    type(sel).season_id_key: sid,    # use the subclass’ key
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

    @staticmethod
    def _movie_extra_type(raw: dict[str, Any]) -> str:
        """Map Daily Wire metadata (or, as a fallback, its title) to one stable type."""
        aliases = {
            'behindthescenes': 'behindthescenes',
            'makingof': 'behindthescenes',
            'deleted': 'deleted',
            'deletedscene': 'deleted',
            'deletedscenes': 'deleted',
            'featurette': 'featurette',
            'interview': 'interview',
            'scene': 'scene',
            'clip': 'scene',
            'short': 'short',
            'shortfilm': 'short',
            'trailer': 'trailer',
            'teaser': 'trailer',
            'other': 'other',
        }
        for field in ('movieExtraType', 'extraType', 'contentType'):
            value = ''.join(character for character in str(raw.get(field) or '').casefold() if character.isalnum())
            if value in aliases:
                return aliases[value]

        title = str(raw.get('title') or '').casefold()
        compact_title = ''.join(character if character.isalnum() else ' ' for character in title)
        words = f" {compact_title} "
        if 'behind the scenes' in title or 'behind-the-scenes' in title or 'making of' in title:
            return 'behindthescenes'
        if 'deleted scene' in title:
            return 'deleted'
        if 'featurette' in title:
            return 'featurette'
        if 'interview' in title:
            return 'interview'
        if 'trailer' in title or 'teaser' in title:
            return 'trailer'
        if 'short film' in title or ' short ' in words:
            return 'short'
        if ' scene ' in words or ' clip ' in words:
            return 'scene'
        return 'other'




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
            # Background/bulk callers use the global pacing policy. Explicitly
            # interactive clients bypass only this wait; retries and network
            # timeouts remain unchanged.
            if self._pace_requests:
                _wait_before_request()

            req = Request(url, headers=self._headers, method='GET')
            try:
                with urlopen(req, timeout=self._req_timeout) as resp:
                    data = resp.read()
                break
            except HTTPError as e:
                try:
                    err_body = e.read().decode('utf-8', errors='ignore')
                except Exception:
                    err_body = ''
                if e.code in self._TRANSIENT_HTTP_CODES and attempt < self._TRANSIENT_RETRIES:
                    time.sleep(self._TRANSIENT_RETRY_DELAY_S * (attempt + 1))
                    continue
                raise MiddlewareAPIError(f"HTTP error {e.code}: {err_body or e.reason}", status_code=e.code) from e
            except URLError as e:
                if attempt < self._TRANSIENT_RETRIES:
                    time.sleep(self._TRANSIENT_RETRY_DELAY_S * (attempt + 1))
                    continue
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