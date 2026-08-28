from __future__ import annotations

import mimetypes
from datetime import timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from backend.db.models import Episode, LocalMediaProfile, RssStreamProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import PreferredFormat

# A download is only fit to stream once the file watcher has confirmed the
# file exists at (or near) its expected size - "pending"/"error"/"missing"/
# "corrupted" downloads are never offered.
_AVAILABLE_STATUSES = {MediaDownloadStatus.DOWNLOADED.value, MediaDownloadStatus.REDOWNLOADED.value}

# Requested video height per preferred format; mirrors the download worker's
# own FORMAT_HEIGHTS so "closest available" picks the same way on both ends.
_VIDEO_HEIGHTS = {
    PreferredFormat.FORMAT_4K.value: 2160,
    PreferredFormat.FORMAT_1080P.value: 1080,
    PreferredFormat.FORMAT_720P.value: 720,
}

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"


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
    """Pick which of an episode's available downloads a stream profile should serve.

    Mirrors what the Stream Profile form tells the user: never mix audio and
    video, prefer an exact format match, and otherwise fall back to whatever
    else is available in the same family unless an exact match is required.
    """
    wants_audio = preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    candidates = [d for d in downloads if _is_audio_download(d) == wants_audio]
    if not candidates:
        return None

    exact = [d for d in candidates if d.local_media_profile.preferred_format == preferred_format]
    if exact:
        return max(exact, key=lambda d: d.finished_at or d.updated_at)

    # Audio-only is a single bucket, so a non-empty audio `candidates` is
    # always an exact match and never reaches here - this is always a video
    # preference falling back to another available resolution.
    if require_exact_match:
        return None

    desired_height = _VIDEO_HEIGHTS.get(preferred_format, 0)
    at_least = [d for d in candidates if _VIDEO_HEIGHTS.get(d.local_media_profile.preferred_format, 0) >= desired_height]
    pool = at_least or candidates
    return min(pool, key=lambda d: _VIDEO_HEIGHTS.get(d.local_media_profile.preferred_format, 0))


def get_feed_items(s: Session, profile: RssStreamProfile) -> list[tuple[Episode, EpisodeMediaDownload]]:
    """Episodes eligible for this profile's feed, newest first.

    Only ``use_downloads`` is implemented so far: streaming straight from
    Daily Wire for episodes with no matching download (``use_dw_stream``) is
    a later step, so such episodes are simply omitted from the feed for now.
    """
    if not profile.use_downloads:
        return []

    rows = (
        s.query(Episode, EpisodeMediaDownload)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
        .options(joinedload(EpisodeMediaDownload.local_media_profile))
        .filter(Episode.show_id == profile.show_id)
        .filter(EpisodeMediaDownload.download_status.in_(_AVAILABLE_STATUSES))
        .all()
    )

    by_episode: dict[int, tuple[Episode, list[EpisodeMediaDownload]]] = {}
    for episode, download in rows:
        _, downloads = by_episode.setdefault(episode.id, (episode, []))
        downloads.append(download)

    items: list[tuple[Episode, EpisodeMediaDownload]] = []
    for episode, downloads in by_episode.values():
        best = _select_best_download(
            downloads,
            preferred_format=profile.preferred_format,
            require_exact_match=profile.require_exact_match,
        )
        if best is not None:
            items.append((episode, best))

    def sort_key(pair: tuple[Episode, EpisodeMediaDownload]):
        dt = pair[0].published_date or pair[0].went_live_date or pair[0].created_at
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    items.sort(key=sort_key, reverse=True)
    return items


def get_download_for_episode(s: Session, profile: RssStreamProfile, episode_slug: str) -> EpisodeMediaDownload:
    """The one download this profile would serve for a single episode, by slug."""
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug, show_id=profile.show_id)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    if not profile.use_downloads:
        raise HTTPException(status_code=404, detail="This feed does not stream downloaded media")

    downloads = (
        s.query(EpisodeMediaDownload)
        .options(joinedload(EpisodeMediaDownload.local_media_profile))
        .filter(EpisodeMediaDownload.media_item_id == episode.id)
        .filter(EpisodeMediaDownload.download_status.in_(_AVAILABLE_STATUSES))
        .all()
    )
    best = _select_best_download(
        downloads,
        preferred_format=profile.preferred_format,
        require_exact_match=profile.require_exact_match,
    )
    if best is None:
        raise HTTPException(status_code=404, detail="No downloaded media available for this episode")
    return best


def _sub_text(parent: Element, tag: str, text: Optional[str]) -> Element:
    el = SubElement(parent, tag)
    el.text = text
    return el


def _append_item(channel: Element, *, media_base_url: str, episode: Episode, download: EpisodeMediaDownload) -> None:
    item = SubElement(channel, "item")
    _sub_text(item, "title", episode.title)

    guid = SubElement(item, "guid", {"isPermaLink": "false"})
    guid.text = episode.uuid

    if episode.description:
        _sub_text(item, "description", episode.description)

    pub_date = episode.published_date or episode.went_live_date or episode.created_at
    if pub_date is not None:
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        _sub_text(item, "pubDate", format_datetime(pub_date))

    file_path = Path(download.file_path)
    length = file_path.stat().st_size if file_path.is_file() else (download.downloaded_bytes or 0)
    default_type = "audio/mpeg" if _is_audio_download(download) else "video/mp4"
    mime_type = mimetypes.guess_type(file_path.name)[0] or default_type

    media_url = f"{media_base_url}/episodes/{episode.slug}"
    SubElement(item, "enclosure", {"url": media_url, "length": str(length), "type": mime_type})
    _sub_text(item, "link", media_url)

    _sub_text(item, "itunes:duration", str(int(round(episode.duration))) if episode.duration else "0")

    image_url = episode.thumbnail_landscape_path or episode.thumbnail_square_path or episode.thumbnail_portrait_path
    if image_url:
        SubElement(item, "itunes:image", {"href": image_url})


def render_rss_feed(s: Session, request: Request, profile: RssStreamProfile) -> bytes:
    show = profile.show
    items = get_feed_items(s, profile)

    base = str(request.base_url).rstrip("/")
    media_base_url = f"{base}/feeds/rss/{profile.token}"

    rss = Element("rss", {"version": "2.0", "xmlns:itunes": _ITUNES_NS})
    channel = SubElement(rss, "channel")
    _sub_text(channel, "title", show.title)
    _sub_text(channel, "link", show.sharing_url)
    _sub_text(channel, "description", show.description or show.title)
    _sub_text(channel, "language", "en-us")
    _sub_text(channel, "generator", "WireLoft")
    _sub_text(channel, "itunes:author", show.author_name)
    _sub_text(channel, "itunes:explicit", "false")

    image_url = show.thumbnail_square_path or show.thumbnail_landscape_path or show.logo_image_path
    if image_url:
        SubElement(channel, "itunes:image", {"href": image_url})
        image = SubElement(channel, "image")
        _sub_text(image, "url", image_url)
        _sub_text(image, "title", show.title)
        _sub_text(image, "link", show.sharing_url)

    for episode, download in items:
        _append_item(channel, media_base_url=media_base_url, episode=episode, download=download)

    return tostring(rss, encoding="UTF-8", xml_declaration=True)
