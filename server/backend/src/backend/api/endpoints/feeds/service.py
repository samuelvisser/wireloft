from __future__ import annotations

import logging
import mimetypes
import re
from email.utils import format_datetime
from pathlib import Path
from typing import Literal, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from config.network import is_no_internet_error
from .cached_video import get_cached_mp4_size
from backend.db.datetime_types import utc_datetime
from backend.db.models import (
    DownloadProfileBase,
    Episode,
    LocalMediaProfile,
    RssStreamProfile,
    SeriesDownloadProfile,
)
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.episode_types import EpisodePublishStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import (
    DEFAULT_RSS_DW_VIDEO_METHOD,
    RSS_HLS_VIDEO_METHODS,
    RssDwVideoMethod,
)
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


logger = logging.getLogger(__name__)

_AVAILABLE_ARTIFACT_STATUS = MediaDownloadArtifactStatus.AVAILABLE.value
_RECONCILABLE_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_UNAVAILABLE_PUBLISH_STATUSES = {
    EpisodePublishStatus.NO_USABLE_MEDIA.value,
    EpisodePublishStatus.DW_PROCESSING.value,
}
_VIDEO_HEIGHTS = {
    PreferredFormat.FORMAT_4K.value: 2160,
    PreferredFormat.FORMAT_1080P.value: 1080,
    PreferredFormat.FORMAT_720P.value: 720,
}

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_PODCAST_NS = "https://podcastindex.org/namespace/1.0"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_HLS_MIME_TYPE = "application/x-mpegURL"
_BARE_HTML_AMPERSAND_RE = re.compile(
    r"&(?!(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)"
)
_CACHED_MP4_METHODS = {
    RssDwVideoMethod.STREAM_DOWNLOAD_MP4.value,
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_MP4.value,
}
_HLS_ALTERNATE_METHODS = {
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_M4A.value,
    RssDwVideoMethod.STREAM_HLS_DOWNLOAD_MP4.value,
}


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
    """Pick the local artifact that best matches a stream profile."""
    wants_audio = preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    candidates = [d for d in downloads if _is_audio_download(d) == wants_audio]
    if not candidates:
        return None

    exact = [
        d for d in candidates
        if d.local_media_profile.preferred_format == preferred_format
    ]
    if exact:
        return max(exact, key=lambda d: d.downloaded_at or d.updated_at)

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


def _select_best_resolvable_download(
        s: Session,
        downloads: list[EpisodeMediaDownload],
        *,
        preferred_format: str,
        require_exact_match: bool,
) -> Optional[EpisodeMediaDownload]:
    """Pick the best local artifact that can actually be resolved on disk."""
    remaining = list(downloads)
    while remaining:
        best = _select_best_download(
            remaining,
            preferred_format=preferred_format,
            require_exact_match=require_exact_match,
        )
        if best is None:
            return None
        resolved = resolve_media_download_file(
            s,
            best,
            release_read_transaction=True,
        )
        if resolved is not None and best.artifact_status == _AVAILABLE_ARTIFACT_STATUS:
            return best
        remaining.remove(best)
    return None


def _episode_type_prefix(episode: Episode) -> str:
    return episode.episode_type or ""


def _profile_allows_episode(profile: RssStreamProfile, episode: Episode) -> bool:
    return _episode_type_prefix(episode) in set(profile.ep_id_type_list or [])


def _profile_streams_live_hls(profile: RssStreamProfile) -> bool:
    return (
        profile.stream_live_episodes
        and profile.preferred_format != PreferredFormat.FORMAT_AUDIO_ONLY.value
        and profile.dw_video_method in RSS_HLS_VIDEO_METHODS
    )


def _has_video_download_profile_for_episode(
        s: Session,
        episode: Episode,
) -> bool:
    """Return whether an enabled Download Profile will retain this live type."""
    episode_type = _episode_type_prefix(episode)
    profiles = (
        s.query(DownloadProfileBase)
        .options(joinedload(DownloadProfileBase.local_media_profile))
        .filter(
            DownloadProfileBase.show_id == episode.show_id,
            DownloadProfileBase.enable_profile.is_(True),
        )
        .all()
    )
    for download_profile in profiles:
        if episode_type not in set(download_profile.ep_id_type_list or []):
            continue
        if (
            download_profile.local_media_profile.preferred_format
            == PreferredFormat.FORMAT_AUDIO_ONLY.value
        ):
            continue
        if isinstance(download_profile, SeriesDownloadProfile):
            if episode.season_id not in {
                season.id for season in download_profile.seasons
            }:
                continue
        return True
    return False


def _can_stream_live_episode(
        s: Session,
        profile: RssStreamProfile,
        episode: Episode,
) -> bool:
    if not _profile_streams_live_hls(profile):
        return False
    if profile.use_dw_stream:
        return True
    return (
        profile.use_downloads
        and _has_video_download_profile_for_episode(s, episode)
    )


def get_feed_items(
        s: Session,
        profile: RssStreamProfile,
) -> list[tuple[Episode, Optional[EpisodeMediaDownload]]]:
    """Return eligible episodes newest first and maintain live handoff state."""
    live_hls_enabled = _profile_streams_live_hls(profile)
    if (
        not profile.use_downloads
        and not profile.use_dw_stream
        and not live_hls_enabled
    ):
        return []

    episodes = (
        s.query(Episode)
        .filter(Episode.show_id == profile.show_id)
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
                EpisodeMediaDownload.artifact_status.in_(_RECONCILABLE_ARTIFACT_STATUSES)
            )
            .all()
        )
        for download in rows:
            downloads_by_episode.setdefault(
                download.media_item_id,
                [],
            ).append(download)

    previous_handoffs = set(profile.live_episode_handoff_ids or [])
    next_handoffs: set[int] = set()
    items: list[tuple[Episode, Optional[EpisodeMediaDownload]]] = []

    for episode in episodes:
        if not _profile_allows_episode(profile, episode):
            continue

        is_live = episode.publish_status == EpisodePublishStatus.LIVE.value
        if is_live:
            if not _can_stream_live_episode(s, profile, episode):
                continue
            # A local file can only represent an earlier/static artifact while
            # the episode itself is live. Force HLS so this item is genuinely live.
            items.append((episode, None))
            if not profile.use_dw_stream:
                next_handoffs.add(episode.id)
            continue

        best = None
        if profile.use_downloads:
            best = _select_best_resolvable_download(
                s,
                downloads_by_episode.get(episode.id, []),
                preferred_format=profile.preferred_format,
                require_exact_match=profile.require_exact_match,
            )

        if best is not None:
            # The first usable local artifact completes the temporary live ->
            # download bridge. Do not preserve the handoff after this point.
            items.append((episode, best))
            continue

        if episode.id in previous_handoffs and live_hls_enabled:
            # This episode was exposed while live with normal Daily Wire
            # streaming disabled. Keep its remote HLS path alive until the
            # configured Download Profile produces the first usable video.
            items.append((episode, None))
            next_handoffs.add(episode.id)
            continue

        if episode.publish_status in _UNAVAILABLE_PUBLISH_STATUSES:
            continue

        if profile.use_dw_stream:
            items.append((episode, None))

    normalized_handoffs = sorted(next_handoffs)
    if list(profile.live_episode_handoff_ids or []) != normalized_handoffs:
        profile.live_episode_handoff_ids = normalized_handoffs

    def sort_key(pair: tuple[Episode, Optional[EpisodeMediaDownload]]):
        episode = pair[0]
        value = (
            episode.published_date
            or episode.went_live_date
            or episode.created_at
        )
        return utc_datetime(value)

    items.sort(key=sort_key, reverse=True)
    return items[:profile.max_items] if profile.max_items > 0 else items


def get_media_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> tuple[Episode, Optional[EpisodeMediaDownload]]:
    """Resolve an enclosure to a local artifact or an allowed remote fallback."""
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug, show_id=profile.show_id)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not _profile_allows_episode(profile, episode):
        raise HTTPException(status_code=404, detail="Episode not included in this feed")

    if episode.publish_status == EpisodePublishStatus.LIVE.value:
        if _can_stream_live_episode(s, profile, episode):
            return episode, None
        raise HTTPException(
            status_code=404,
            detail="Live episode streaming is not available for this episode",
        )

    best = None
    if profile.use_downloads:
        downloads = (
            s.query(EpisodeMediaDownload)
            .options(joinedload(EpisodeMediaDownload.local_media_profile))
            .filter(EpisodeMediaDownload.media_item_id == episode.id)
            .filter(
                EpisodeMediaDownload.artifact_status.in_(_RECONCILABLE_ARTIFACT_STATUSES)
            )
            .all()
        )
        best = _select_best_resolvable_download(
            s,
            downloads,
            preferred_format=profile.preferred_format,
            require_exact_match=profile.require_exact_match,
        )

    if best is not None:
        return episode, best

    if (
        episode.id in set(profile.live_episode_handoff_ids or [])
        and _profile_streams_live_hls(profile)
    ):
        return episode, None

    if episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value:
        raise HTTPException(status_code=404, detail="Episode has no usable media")
    if episode.publish_status == EpisodePublishStatus.DW_PROCESSING.value:
        raise HTTPException(status_code=404, detail="Episode media is still processing")

    if profile.use_dw_stream:
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
    """Return the local artifact this profile would serve for one episode."""
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
        if is_no_internet_error(exc):
            raise
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
) -> None:
    attributes = {
        "type": _HLS_MIME_TYPE,
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
) -> None:
    item = SubElement(channel, "item")
    _sub_text(item, "title", episode.title)

    wants_audio = preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    guid_value = episode.uuid
    if download is None and not wants_audio:
        guid_value = f"{guid_value}:{dw_video_method}"

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
        _sub_text(item, "pubDate", format_datetime(utc_datetime(pub_date)))

    media_url = f"{media_base_url}/episodes/{episode.slug}"
    if download is not None:
        file_path = Path(download.file_path)
        length = download.artifact_size_bytes or download.downloaded_bytes or 0
        default_type = (
            "audio/mpeg" if _is_audio_download(download) else "video/mp4"
        )
        mime_type = mimetypes.guess_type(file_path.name)[0] or default_type
        enclosure_url = media_url
    elif wants_audio:
        length = 0
        mime_type = "audio/mpeg"
        enclosure_url = media_url
    elif dw_video_method in _CACHED_MP4_METHODS:
        length = get_cached_mp4_size(episode.uuid) or 0
        mime_type = "video/mp4"
        enclosure_url = f"{media_url}/video.mp4"
    else:
        length = 0
        mime_type = "audio/mpeg"
        enclosure_url = f"{media_url}/audio"

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

    if (
        download is None
        and not wants_audio
        and dw_video_method in _HLS_ALTERNATE_METHODS
        and dw_video_url
    ):
        _append_hls_alternate(
            item,
            video_url=dw_video_url,
            preferred_format=preferred_format,
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

    client: MiddlewareClient | None = None
    for episode, download in items:
        dw_video_url = None
        if (
            download is None
            and profile.preferred_format
            != PreferredFormat.FORMAT_AUDIO_ONLY.value
            and dw_video_method in _HLS_ALTERNATE_METHODS
        ):
            client = client or MiddlewareClient()
            try:
                dw_video_url = get_dailywire_stream_url(
                    profile,
                    episode,
                    media_kind="video",
                    client=client,
                )
            except HTTPException as exc:
                logger.warning(
                    "Could not add Daily Wire video stream for episode '%s': %s",
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
        )

    return tostring(rss, encoding="UTF-8", xml_declaration=True)