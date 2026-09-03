from __future__ import annotations

import logging
import mimetypes
import re
from datetime import timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Literal, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from .cached_video import get_cached_mp4_size
from .hls_experiments import (
    HLS_APPLE_MPEGURL,
    HLS_GENERIC_MPEGURL,
    HLS_X_MPEGURL,
)
from .hls_probe_experiments import (
    prewarm_hls_manifests,
    remember_prefetched_hls_url,
)
from backend.db.models import Episode, LocalMediaProfile, RssStreamProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import (
    DEFAULT_RSS_DW_VIDEO_METHOD,
    RssDwVideoMethod,
)
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient


logger = logging.getLogger(__name__)

_AVAILABLE_STATUSES = {
    MediaDownloadStatus.DOWNLOADED.value,
    MediaDownloadStatus.REDOWNLOADED.value,
}
_VIDEO_HEIGHTS = {
    PreferredFormat.FORMAT_4K.value: 2160,
    PreferredFormat.FORMAT_1080P.value: 1080,
    PreferredFormat.FORMAT_720P.value: 720,
}

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_PODCAST_NS = "https://podcastindex.org/namespace/1.0"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_BARE_HTML_AMPERSAND_RE = re.compile(
    r"&(?!(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)"
)
_CACHED_MP4_METHODS = {
    RssDwVideoMethod.STREAM_DOWNLOAD_MP4.value,
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_MP4.value,
    "cached_mp4",
    "podcasting_2_0_cached_mp4",
}
_EMBEDDED_HLS_METHODS = {
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_M4A.value,
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_MP4.value,
    "podcasting_2_0",
    "podcasting_2_0_cached_mp4",
}
_PREFETCH_URL_METHODS = {
    RssDwVideoMethod.EXPERIMENT_HLS_CACHED_REDIRECT_302.value,
}
_PREFETCH_MANIFEST_METHODS = {
    RssDwVideoMethod.EXPERIMENT_HLS_PREWARMED_RAW.value,
    RssDwVideoMethod.EXPERIMENT_HLS_PREWARMED_ABSOLUTE.value,
}
_FORCE_HTTPS_HLS_METHODS = {
    RssDwVideoMethod.EXPERIMENT_HLS_HTTPS_REDIRECT_302.value,
}
_FEED_RESOLVED_HLS_METHODS = (
    _EMBEDDED_HLS_METHODS
    | _PREFETCH_URL_METHODS
    | _PREFETCH_MANIFEST_METHODS
)
_STABLE_HLS_SOURCES: dict[str, tuple[str, str]] = {
    RssDwVideoMethod.EXPERIMENT_HLS_REDIRECT_302.value: (
        "video.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_HTTPS_REDIRECT_302.value: (
        "video-https.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_CACHED_REDIRECT_302.value: (
        "video-cached-302.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_HEAD_200_GET_302.value: (
        "video-head200.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_REDIRECT_302_HEADERS.value: (
        "video-302-headers.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PREWARMED_RAW.value: (
        "video-prewarmed-raw.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PREWARMED_ABSOLUTE.value: (
        "video-prewarmed-absolute.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_REDIRECT_307.value: (
        "video-307.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_REDIRECT_308.value: (
        "video-308.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PROXY_VIDEO_X.value: (
        "video-proxy.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PROXY_MASTER_X.value: (
        "master.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PROXY_INDEX_X.value: (
        "index.m3u8",
        HLS_X_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PROXY_VIDEO_APPLE.value: (
        "video-proxy-apple.m3u8",
        HLS_APPLE_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PROXY_VIDEO_GENERIC.value: (
        "video-proxy-generic.m3u8",
        HLS_GENERIC_MPEGURL,
    ),
    RssDwVideoMethod.EXPERIMENT_HLS_PREPARED_TS.value: (
        "prepared/video.m3u8",
        HLS_X_MPEGURL,
    ),
}
_HLS_ALTERNATE_METHODS = _EMBEDDED_HLS_METHODS | set(_STABLE_HLS_SOURCES)


def get_rss_stream_profile_by_token(s: Session, token: str) -> RssStreamProfile:
    item: Optional[RssStreamProfile] = (
        s.query(RssStreamProfile)
        .options(joinedload(RssStreamProfile.show))
        .filter_by(token=token)
        .one_or_none()
    )
    if item is None or not item.enable_profile:
        raise HTTPException(status_code=404, detail="Feed not found")
    return item


def _is_audio_download(download: EpisodeMediaDownload) -> bool:
    profile: LocalMediaProfile = download.local_media_profile
    return profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value


def _select_best_download(
        downloads: list[EpisodeMediaDownload],
        *,
        preferred_format: str,
        require_exact_match: bool,
) -> Optional[EpisodeMediaDownload]:
    """Pick the local download that best matches a stream profile."""
    wants_audio = preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    candidates = [d for d in downloads if _is_audio_download(d) == wants_audio]
    if not candidates:
        return None

    exact = [
        d for d in candidates
        if d.local_media_profile.preferred_format == preferred_format
    ]
    if exact:
        return max(exact, key=lambda d: d.finished_at or d.updated_at)

    if require_exact_match:
        return None

    desired_height = _VIDEO_HEIGHTS.get(preferred_format, 0)
    at_least = [
        d for d in candidates
        if _VIDEO_HEIGHTS.get(d.local_media_profile.preferred_format, 0)
        >= desired_height
    ]
    pool = at_least or candidates
    return min(
        pool,
        key=lambda d: _VIDEO_HEIGHTS.get(
            d.local_media_profile.preferred_format,
            0,
        ),
    )


def _episode_type_prefix(episode: Episode) -> str:
    return episode.episode_identifier.split(".", 1)[0]


def _profile_allows_episode(profile: RssStreamProfile, episode: Episode) -> bool:
    return _episode_type_prefix(episode) in set(profile.ep_id_type_list or [])


def get_feed_items(
        s: Session,
        profile: RssStreamProfile,
) -> list[tuple[Episode, Optional[EpisodeMediaDownload]]]:
    """Return eligible episodes newest first."""
    if not profile.use_downloads and not profile.use_dw_stream:
        return []

    episodes = (
        s.query(Episode)
        .filter(Episode.show_id == profile.show_id)
        .filter(Episode.is_no_show_today.is_not(True))
        .all()
    )

    downloads_by_episode: dict[int, list[EpisodeMediaDownload]] = {}
    if profile.use_downloads:
        rows = (
            s.query(EpisodeMediaDownload)
            .join(Episode, EpisodeMediaDownload.media_item_id == Episode.id)
            .options(joinedload(EpisodeMediaDownload.local_media_profile))
            .filter(Episode.show_id == profile.show_id)
            .filter(
                EpisodeMediaDownload.download_status.in_(_AVAILABLE_STATUSES)
            )
            .all()
        )
        for download in rows:
            downloads_by_episode.setdefault(
                download.media_item_id,
                [],
            ).append(download)

    items: list[tuple[Episode, Optional[EpisodeMediaDownload]]] = []
    for episode in episodes:
        if not _profile_allows_episode(profile, episode):
            continue

        best = None
        if profile.use_downloads:
            best = _select_best_download(
                downloads_by_episode.get(episode.id, []),
                preferred_format=profile.preferred_format,
                require_exact_match=profile.require_exact_match,
            )
        if best is not None or profile.use_dw_stream:
            items.append((episode, best))

    def sort_key(pair: tuple[Episode, Optional[EpisodeMediaDownload]]):
        episode = pair[0]
        value = (
            episode.published_date
            or episode.went_live_date
            or episode.created_at
        )
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    items.sort(key=sort_key, reverse=True)
    return items[:profile.max_items] if profile.max_items > 0 else items


def get_media_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> tuple[Episode, Optional[EpisodeMediaDownload]]:
    """Resolve an enclosure to a local download or a Daily Wire fallback."""
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug, show_id=profile.show_id)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not _profile_allows_episode(profile, episode):
        raise HTTPException(status_code=404, detail="Episode not included in this feed")

    best = None
    if profile.use_downloads:
        downloads = (
            s.query(EpisodeMediaDownload)
            .options(joinedload(EpisodeMediaDownload.local_media_profile))
            .filter(EpisodeMediaDownload.media_item_id == episode.id)
            .filter(
                EpisodeMediaDownload.download_status.in_(_AVAILABLE_STATUSES)
            )
            .all()
        )
        best = _select_best_download(
            downloads,
            preferred_format=profile.preferred_format,
            require_exact_match=profile.require_exact_match,
        )

    if best is not None:
        return episode, best
    if profile.use_dw_stream and episode.is_no_show_today is not True:
        return episode, None

    raise HTTPException(
        status_code=404,
        detail="No media available for this episode",
    )


def get_download_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> EpisodeMediaDownload:
    """Return the local download this profile would serve for one episode."""
    _, download = get_media_for_episode(s, profile, episode_slug)
    if download is None:
        raise HTTPException(
            status_code=404,
            detail="No downloaded media available for this episode",
        )
    return download


def get_dailywire_stream_url(
        profile: RssStreamProfile,
        episode: Episode,
        *,
        media_kind: Literal["audio", "video"] | None = None,
        client: MiddlewareClient | None = None,
) -> str:
    """Fetch a fresh Daily Wire media URL."""
    require_member_exclusive = profile.show.membership_level not in {
        WlDwMembershipLevel.FREE.value,
        WlDwMembershipLevel.WL_ANY.value,
    }
    try:
        detail = (client or MiddlewareClient()).get_episode_details(
            episode.slug,
            require_member_exclusive=require_member_exclusive,
        )
    except MiddlewareAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail="Daily Wire stream is currently unavailable",
        ) from exc

    if media_kind is None:
        media_kind = (
            "audio"
            if profile.preferred_format
            == PreferredFormat.FORMAT_AUDIO_ONLY.value
            else "video"
        )

    media_url = (
        detail.audio_url if media_kind == "audio" else detail.video_url
    )
    if not media_url:
        raise HTTPException(
            status_code=404,
            detail=f"No Daily Wire {media_kind} stream available for this episode",
        )
    return media_url


def _sub_text(parent: Element, tag: str, text: Optional[str]) -> Element:
    element = SubElement(parent, tag)
    element.text = text
    return element


def _escape_bare_html_ampersands(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return _BARE_HTML_AMPERSAND_RE.sub("&amp;", text)


def _append_hls_alternate(
        item: Element,
        *,
        video_url: str,
        preferred_format: str,
        hls_mime_type: str,
) -> None:
    attributes = {
        "type": hls_mime_type,
        "length": "0",
        "bitrate": "2500000",
        "lang": "en",
        "title": "HD Video Stream",
        "rel": "alternate",
    }
    height = _VIDEO_HEIGHTS.get(preferred_format)
    if height is not None:
        attributes["height"] = str(height)

    alternate = SubElement(item, "podcast:alternateEnclosure", attributes)
    SubElement(alternate, "podcast:source", {"uri": video_url})


def _append_item(
        channel: Element,
        *,
        media_base_url: str,
        episode: Episode,
        download: Optional[EpisodeMediaDownload],
        preferred_format: str,
        dw_video_method: str = DEFAULT_RSS_DW_VIDEO_METHOD,
        dw_video_url: str | None = None,
        experiment_guid_scope: str | None = None,
) -> None:
    item = SubElement(channel, "item")
    _sub_text(item, "title", episode.title)

    wants_audio = preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    guid_value = episode.uuid
    if download is None and not wants_audio:
        guid_value = f"{guid_value}:{dw_video_method}"
        if dw_video_method.startswith("experiment_") and experiment_guid_scope:
            guid_value = f"{guid_value}:{experiment_guid_scope}"

    guid = SubElement(item, "guid", {"isPermaLink": "false"})
    guid.text = guid_value

    if episode.description:
        _sub_text(
            item,
            "description",
            _escape_bare_html_ampersands(episode.description),
        )

    pub_date = (
        episode.published_date
        or episode.went_live_date
        or episode.created_at
    )
    if pub_date is not None:
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        _sub_text(item, "pubDate", format_datetime(pub_date))

    media_url = f"{media_base_url}/episodes/{episode.slug}"
    audio_url = f"{media_url}/audio.m4a"
    if download is not None:
        file_path = Path(download.file_path)
        length = (
            file_path.stat().st_size
            if file_path.is_file()
            else (download.downloaded_bytes or 0)
        )
        default_type = (
            "audio/mp4" if _is_audio_download(download) else "video/mp4"
        )
        mime_type = mimetypes.guess_type(file_path.name)[0] or default_type
        suffix = file_path.suffix.lower() or (
            ".m4a" if _is_audio_download(download) else ".mp4"
        )
        enclosure_url = f"{media_url}/download{suffix}"
    elif wants_audio:
        length = 0
        mime_type = "audio/mp4"
        enclosure_url = audio_url
    elif dw_video_method in _CACHED_MP4_METHODS:
        length = get_cached_mp4_size(episode.uuid) or 0
        mime_type = "video/mp4"
        enclosure_url = f"{media_url}/video.mp4"
    else:
        length = 0
        mime_type = "audio/mp4"
        enclosure_url = audio_url

    SubElement(
        item,
        "enclosure",
        {
            "url": enclosure_url,
            "length": str(length),
            "type": mime_type,
        },
    )
    _sub_text(item, "link", media_url)

    if download is None and not wants_audio and dw_video_method in _HLS_ALTERNATE_METHODS:
        video_url = dw_video_url
        hls_mime_type = HLS_X_MPEGURL
        stable_source = _STABLE_HLS_SOURCES.get(dw_video_method)
        if stable_source is not None:
            endpoint, hls_mime_type = stable_source
            video_url = f"{media_url}/{endpoint}"
            if (
                dw_video_method in _FORCE_HTTPS_HLS_METHODS
                and video_url.startswith("http://")
            ):
                video_url = f"https://{video_url[len('http://') :]}"

        if video_url:
            _append_hls_alternate(
                item,
                video_url=video_url,
                preferred_format=preferred_format,
                hls_mime_type=hls_mime_type,
            )

    _sub_text(
        item,
        "itunes:duration",
        str(int(round(episode.duration))) if episode.duration else "0",
    )

    image_url = (
        episode.thumbnail_landscape_path
        or episode.thumbnail_square_path
        or episode.thumbnail_portrait_path
    )
    if image_url:
        SubElement(item, "itunes:image", {"href": image_url})


def render_rss_feed(
        s: Session,
        request: Request,
        profile: RssStreamProfile,
) -> bytes:
    show = profile.show
    items = get_feed_items(s, profile)
    dw_video_method = (
        profile.dw_video_method or DEFAULT_RSS_DW_VIDEO_METHOD
    )

    base = str(request.base_url).rstrip("/")
    media_base_url = f"{base}/feeds/rss/{profile.token}"

    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:itunes": _ITUNES_NS,
            "xmlns:podcast": _PODCAST_NS,
            "xmlns:atom": _ATOM_NS,
        },
    )
    channel = SubElement(rss, "channel")
    _sub_text(channel, "title", show.title)
    _sub_text(channel, "link", show.sharing_url)
    _sub_text(
        channel,
        "description",
        _escape_bare_html_ampersands(show.description or show.title),
    )
    _sub_text(channel, "language", "en-us")
    _sub_text(channel, "generator", "WireLoft")
    _sub_text(channel, "itunes:author", show.author_name)
    _sub_text(channel, "itunes:explicit", "false")
    SubElement(
        channel,
        "atom:link",
        {
            "href": profile.feed_url,
            "rel": "self",
            "type": "application/rss+xml",
        },
    )
    _sub_text(
        channel,
        "podcast:medium",
        "podcast"
        if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
        else "video",
    )

    image_url = (
        show.thumbnail_square_path
        or show.thumbnail_landscape_path
        or show.logo_image_path
    )
    if image_url:
        SubElement(channel, "itunes:image", {"href": image_url})
        image = SubElement(channel, "image")
        _sub_text(image, "url", image_url)
        _sub_text(image, "title", show.title)
        _sub_text(image, "link", show.sharing_url)

    # The normal stable-URL experiments keep feed rendering free of external
    # calls. A few diagnostic methods intentionally resolve or fetch HLS here
    # so Pocket Casts can later probe an already-warm endpoint. Keep those
    # methods limited to small feeds while testing.
    client: MiddlewareClient | None = None
    for episode, download in items:
        dw_video_url = None
        if (
            download is None
            and profile.preferred_format
            != PreferredFormat.FORMAT_AUDIO_ONLY.value
            and dw_video_method in _FEED_RESOLVED_HLS_METHODS
        ):
            client = client or MiddlewareClient()
            try:
                dw_video_url = get_dailywire_stream_url(
                    profile,
                    episode,
                    media_kind="video",
                    client=client,
                )
                cache_key = f"{profile.token}:{episode.slug}"
                if dw_video_method in _PREFETCH_URL_METHODS:
                    remember_prefetched_hls_url(cache_key, dw_video_url)
                elif dw_video_method in _PREFETCH_MANIFEST_METHODS:
                    prewarm_hls_manifests(cache_key, dw_video_url)
            except HTTPException as exc:
                logger.warning(
                    "Could not prepare Daily Wire video experiment for episode '%s': %s",
                    episode.slug,
                    exc.detail,
                )

        _append_item(
            channel,
            media_base_url=media_base_url,
            episode=episode,
            download=download,
            preferred_format=profile.preferred_format,
            dw_video_method=dw_video_method,
            dw_video_url=dw_video_url,
            experiment_guid_scope=profile.token,
        )

    return tostring(rss, encoding="UTF-8", xml_declaration=True)
