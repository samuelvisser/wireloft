from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .middleware.client import MiddlewareClient, MiddlewareAPIError


class DailyWireAPIError(Exception):
    """Generic error raised by DailyWireAPI."""


@dataclass(frozen=True)
class SeasonInfo:
    id: str
    name: Optional[str]
    slug: str


@dataclass(frozen=True)
class ShowInfo:
    id: str
    name: Optional[str]
    description: Optional[str]
    image: Optional[str]
    seasons: List[SeasonInfo]


@dataclass(frozen=True)
class EpisodeRef:
    slug: str
    url: str
    season_slug: Optional[str] = None


class DailyWireAPI:
    """
    Minimal client for DailyWire's Middleware API.

    Focuses on show browsing and listing all episodes for a given show slug.
    Authentication is optional; premium shows may require an access token cookie
    from dailywire.com. If you have a JWT access token, pass it to the constructor.

    Example:
        api = DailyWireAPI(access_token="<JWT or cookies accessToken>")
        episode_slugs = api.list_show_episode_slugs("what-we-saw")
    """

    def __init__(self, access_token: Optional[str] = None, timeout: float = 30.0, membership_plan: Optional[str] = None):
        self._timeout = timeout
        self._membership_plan = membership_plan
        self._mw = MiddlewareClient(access_token=access_token, timeout=timeout)

    # ------------------------ public API ------------------------
    def get_show_by_slug(self, slug: str) -> ShowInfo:
        """Fetch show metadata and seasons for a show slug using Middleware API.

        Raises DailyWireAPIError if the show is not found or on network error.
        """
        try:
            page = self._mw.get_show_page(slug, self._membership_plan)
            return self._map_show_page_to_showinfo(page)
        except MiddlewareAPIError as e:
            raise DailyWireAPIError(str(e)) from e

    def list_show_episode_slugs(self, show_slug: str) -> List[str]:
        """Return a flat list of episode slugs for a show (Middleware only)."""
        try:
            page = self._mw.get_show_page(show_slug, self._membership_plan)
        except MiddlewareAPIError as e:
            raise DailyWireAPIError(str(e)) from e

        slugs = self._extract_episode_slugs_from_show_page(page)
        # unique preserving order
        seen = set()
        result: List[str] = []
        for s in slugs:
            if s and s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def list_show_episodes(self, show_slug: str) -> List[EpisodeRef]:
        """Return a list of EpisodeRef for a show, with canonical episode URLs (Middleware only)."""
        slugs = self.list_show_episode_slugs(show_slug)
        return [EpisodeRef(slug=s, url=f"https://www.dailywire.com/episode/{s}") for s in slugs]

    # ------------------------ mapping helpers ------------------------
    def _extract_episode_slugs_from_show_page(self, page: Dict) -> List[str]:
        slugs: List[str] = []
        seen = set()

        def add_slug(s: Optional[str]):
            if not s:
                return
            if isinstance(s, str):
                s = s.strip()
                if not s:
                    return
                if s not in seen:
                    seen.add(s)
                    slugs.append(s)

        def parse_episode_url(u: str):
            if not isinstance(u, str):
                return
            marker = '/episode/'
            idx = u.find(marker)
            if idx >= 0:
                rest = u[idx + len(marker):]
                # stop at next separator
                for sep in ['?', '#', '/', '"', "'", ' ']:
                    cut = rest.find(sep)
                    if cut >= 0:
                        rest = rest[:cut]
                # basic slug hygiene
                if rest:
                    add_slug(rest)

        def walk(obj: Any, parent_key: Optional[str] = None):
            if isinstance(obj, dict):
                # If this dict directly has an episode slug nested
                if 'episode' in obj and isinstance(obj['episode'], dict):
                    ep_slug = obj['episode'].get('slug')
                    add_slug(ep_slug)
                # Generic slug on objects that look like episodes (heuristic)
                if parent_key and parent_key.lower() in ('episode', 'episodes') and 'slug' in obj:
                    add_slug(obj.get('slug'))
                for k, v in obj.items():
                    # Parse any episode URLs
                    if isinstance(v, str):
                        parse_episode_url(v)
                    walk(v, k)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, parent_key)
            elif isinstance(obj, str):
                parse_episode_url(obj)

        walk(page)
        return slugs

    def _map_show_page_to_showinfo(self, page: Dict) -> ShowInfo:
        slug = None
        show = None
        if isinstance(page, dict):
            show = (
                page.get('show')
                or page.get('data', {}).get('show') if isinstance(page.get('data'), dict) else None
                or page.get('payload', {}).get('show') if isinstance(page.get('payload'), dict) else None
                or page
            )
        if not isinstance(show, dict):
            raise DailyWireAPIError('Show not found')
        # Identify slug if present in response context
        slug = show.get('slug') or page.get('slug')
        name = show.get('name') or show.get('title')
        description = show.get('description') or show.get('summary')
        image = show.get('image') or show.get('thumbnail') or show.get('coverImage')
        show_id = show.get('id') or (slug or 'unknown')

        seasons_raw = (
            show.get('seasons')
            or show.get('seasonList')
            or show.get('seasonGroups')
            or []
        )
        seasons: List[SeasonInfo] = []
        if isinstance(seasons_raw, list):
            for s in seasons_raw:
                if not isinstance(s, dict):
                    continue
                sid = s.get('id') or s.get('seasonId') or s.get('uuid') or s.get('slug')
                sslug = s.get('slug') or s.get('code') or s.get('name')
                sname = s.get('name') or s.get('title') or sslug
                if sid and sslug:
                    seasons.append(SeasonInfo(id=str(sid), name=sname, slug=str(sslug)))
        return ShowInfo(id=str(show_id), name=name, description=description, image=image, seasons=seasons)
