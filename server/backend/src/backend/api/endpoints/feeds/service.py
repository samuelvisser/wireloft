from __future__ import annotations

import logging
import re
from email.utils import format_datetime
from typing import Literal, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead
from backend.db.datetime_types import utc_datetime
from backend.db.models import (
    DownloadProfileBase,
    Episode,
    RssStreamProfile,
    SeriesDownloadProfile,
)
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.download_profile_types import EpIdType, MediaDownloadArtifactStatus
from backend.types.episode_types import EpisodeExtraType, EpisodePublishStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.show_types import EpisodeIdentifier, ShowType
from backend.types.stream_profile_types import (
    RSS_AUDIO_PRIMARY_OUTPUT_MODES,
    RSS_HLS_OUTPUT_MODES,
    RssVideoOutputMode,
)
from config.network import is_no_internet_error
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


def _download_kind(download: EpisodeMediaDownload) -> Literal["audio", "mp4", "hls"]:
    preferred = download.local_media_profile.preferred_format
    if preferred == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        return "audio"
    if preferred == PreferredFormat.FORMAT_HLS.value:
        return "hls"
    return "mp4"


def _candidate_downloads(
        downloads: list[EpisodeMediaDownload],
        *,
        kind: Literal["audio", "mp4", "hls"],
        preferred_format: str,
        prefer_exact_match: bool,
) -> list[EpisodeMediaDownload]:
    candidates = [download for download in downloads if _download_kind(download) == kind]
    if not candidates:
        return []

    if kind != "mp4":
        return sorted(
            candidates,
            key=lambda download: download.downloaded_at or download.updated_at,
            reverse=True,
        )

    exact = [
        download
        for download in candidates
        if download.local_media_profile.preferred_format == preferred_format
    ]
    if exact:
        remaining = [download for download in candidates if download not in exact]
        return sorted(
            exact,
            key=lambda download: download.downloaded_at or download.updated_at,
            reverse=True,
        ) + remaining

    if prefer_exact_match and preferred_format in _VIDEO_HEIGHTS:
        return []

    desired_height = _VIDEO_HEIGHTS.get(
        preferred_format,
        _VIDEO_HEIGHTS[PreferredFormat.FORMAT_1080P.value],
    )
    return sorted(
        candidates,
        key=lambda download: (
            abs(
                _VIDEO_HEIGHTS.get(
                    download.local_media_profile.preferred_format,
                    desired_height,
                )
                - desired_height
            ),
            -_VIDEO_HEIGHTS.get(
                download.local_media_profile.preferred_format,
                0,
            ),
        ),
    )


def _select_resolvable_download(
        s: Session,
        downloads: list[EpisodeMediaDownload],
        *,
        kind: Literal["audio", "mp4", "hls"],
        preferred_format: str,
        prefer_exact_match: bool,
) -> Optional[EpisodeMediaDownload]:
    for candidate in _candidate_downloads(
        downloads,
        kind=kind,
        preferred_format=preferred_format,
        prefer_exact_match=prefer_exact_match,
    ):
        path = resolve_media_download_file(
            s,
            candidate,
            release_read_transaction=True,
        )
        if path is None or candidate.artifact_status != _AVAILABLE_ARTIFACT_STATUS:
            continue
        if kind == "mp4" and path.suffix.lower() != ".mp4":
            continue
        if kind == "hls" and path.suffix.lower() != ".m3u8":
            continue
        return candidate
    return None


def _episode_downloads(
        s: Session,
        profile: RssStreamProfile,
        episode_id: int,
) -> list[EpisodeMediaDownload]:
    if not profile.use_downloads:
        return []
    return (
        s.query(EpisodeMediaDownload)
        .options(joinedload(EpisodeMediaDownload.local_media_profile))
        .filter(EpisodeMediaDownload.media_item_id == episode_id)
        .filter(
            EpisodeMediaDownload.artifact_status.in_(_RECONCILABLE_ARTIFACT_STATUSES)
        )
        .all()
    )


def get_local_download_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode: Episode,
        *,
        kind: Literal["audio", "mp4", "hls"],
) -> Optional[EpisodeMediaDownload]:
    return _select_resolvable_download(
        s,
        _episode_downloads(s, profile, episode.id),
        kind=kind,
        preferred_format=profile.preferred_format,
        prefer_exact_match=profile.prefer_exact_match,
    )


def _mode_downloads(
        s: Session,
        profile: RssStreamProfile,
        downloads: list[EpisodeMediaDownload],
) -> tuple[
    Optional[EpisodeMediaDownload],
    Optional[EpisodeMediaDownload],
    Optional[EpisodeMediaDownload],
]:
    audio = _select_resolvable_download(
        s,
        downloads,
        kind="audio",
        preferred_format=profile.preferred_format,
        prefer_exact_match=False,
    )
    mp4 = _select_resolvable_download(
        s,
        downloads,
        kind="mp4",
        preferred_format=profile.preferred_format,
        prefer_exact_match=profile.prefer_exact_match,
    )
    hls = _select_resolvable_download(
        s,
        downloads,
        kind="hls",
        preferred_format=profile.preferred_format,
        prefer_exact_match=False,
    )
    return audio, mp4, hls


def _relevant_local_download(
        profile: RssStreamProfile,
        *,
        audio: Optional[EpisodeMediaDownload],
        mp4: Optional[EpisodeMediaDownload],
        hls: Optional[EpisodeMediaDownload],
) -> Optional[EpisodeMediaDownload]:
    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        return audio

    mode = profile.video_output_mode
    if mode == RssVideoOutputMode.AUDIO_HLS.value:
        return audio or hls
    if mode == RssVideoOutputMode.AUDIO_MP4.value:
        return audio or mp4
    if mode == RssVideoOutputMode.MP4_HLS.value:
        return mp4 or hls
    return mp4


def _has_required_local_media(
        profile: RssStreamProfile,
        *,
        audio: Optional[EpisodeMediaDownload],
        mp4: Optional[EpisodeMediaDownload],
        hls: Optional[EpisodeMediaDownload],
) -> bool:
    """Whether every enclosure advertised by this profile is available locally.

    Download-only feeds must never publish a stable media URL that can only be
    satisfied by The Daily Wire. When remote streaming is enabled, partial local
    coverage is fine because each stable URL can independently fall back at
    request time.
    """
    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        return audio is not None

    mode = profile.video_output_mode
    if mode == RssVideoOutputMode.AUDIO_HLS.value:
        return audio is not None and hls is not None
    if mode == RssVideoOutputMode.AUDIO_MP4.value:
        return audio is not None and mp4 is not None
    if mode == RssVideoOutputMode.MP4_HLS.value:
        return mp4 is not None and hls is not None
    return mp4 is not None


def _episode_type_prefix(episode: Episode) -> str:
    return episode.episode_type or ""


def _profile_allows_episode(profile: RssStreamProfile, episode: Episode) -> bool:
    return _episode_type_prefix(episode) in set(profile.ep_id_type_list or [])


def _profile_streams_live_hls(profile: RssStreamProfile) -> bool:
    return (
        bool(profile.stream_live_episodes)
        and profile.preferred_format != PreferredFormat.FORMAT_AUDIO_ONLY.value
        and profile.video_output_mode in RSS_HLS_OUTPUT_MODES
    )


def _profile_keeps_live_handoff(profile: RssStreamProfile) -> bool:
    return (
        _profile_streams_live_hls(profile)
        and not profile.use_dw_stream
        and profile.use_downloads
    )


def _has_hls_download_profile_for_episode(
        s: Session,
        episode: Episode,
) -> bool:
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
            != PreferredFormat.FORMAT_HLS.value
        ):
            continue
        if isinstance(download_profile, SeriesDownloadProfile):
            selected_seasons = list(download_profile.seasons)
            selected_season_ids = {season.id for season in selected_seasons}
            if episode.season_id not in selected_season_ids:
                max_selected_index = (
                    max(season.index for season in selected_seasons)
                    if selected_seasons
                    else None
                )
                is_upcoming = (
                    download_profile.include_upcoming_seasons
                    and max_selected_index is not None
                    and episode.season is not None
                    and episode.season.index > max_selected_index
                )
                if not is_upcoming:
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
        and _has_hls_download_profile_for_episode(s, episode)
    )


def can_use_dailywire_for_episode(
        profile: RssStreamProfile,
        episode: Episode,
) -> bool:
    if profile.use_dw_stream:
        return True
    if not _profile_keeps_live_handoff(profile):
        return False
    if episode.publish_status == EpisodePublishStatus.LIVE.value:
        return True
    return episode.id in set(profile.live_episode_handoff_ids or [])


def remember_live_episode_handoff(
        profile: RssStreamProfile,
        episode: Episode,
) -> None:
    if (
        not _profile_keeps_live_handoff(profile)
        or episode.publish_status != EpisodePublishStatus.LIVE.value
    ):
        return
    ids = set(profile.live_episode_handoff_ids or [])
    if episode.id not in ids:
        ids.add(episode.id)
        profile.live_episode_handoff_ids = sorted(ids)


def _download_completes_live_handoff(
        download: EpisodeMediaDownload,
) -> bool:
    return (
        _download_kind(download) == "hls"
        and download.downloaded_publish_status
        == EpisodePublishStatus.PUBLISHED_FINAL.value
    )


def get_feed_items(
        s: Session,
        profile: RssStreamProfile,
) -> list[tuple[Episode, Optional[EpisodeMediaDownload]]]:
    """Return eligible episodes newest first while preserving live HLS continuity."""
    live_enabled = _profile_streams_live_hls(profile)
    if not profile.use_downloads and not profile.use_dw_stream and not live_enabled:
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
            downloads_by_episode.setdefault(download.media_item_id, []).append(download)

    previous_handoffs = set(profile.live_episode_handoff_ids or [])
    next_handoffs: set[int] = set()
    items: list[tuple[Episode, Optional[EpisodeMediaDownload]]] = []

    for episode in episodes:
        if not _profile_allows_episode(profile, episode):
            continue

        is_live = episode.publish_status == EpisodePublishStatus.LIVE.value
        if is_live:
            if _can_stream_live_episode(s, profile, episode):
                items.append((episode, None))
                if (
                    episode.id in previous_handoffs
                    and _profile_keeps_live_handoff(profile)
                ):
                    next_handoffs.add(episode.id)
            continue

        downloads = downloads_by_episode.get(episode.id, [])
        audio, mp4, hls = _mode_downloads(s, profile, downloads)
        relevant_local = _relevant_local_download(
            profile,
            audio=audio,
            mp4=mp4,
            hls=hls,
        )

        handoff_active = (
            episode.id in previous_handoffs
            and _profile_keeps_live_handoff(profile)
        )
        if handoff_active and hls is not None and _download_completes_live_handoff(hls):
            handoff_active = False

        if handoff_active:
            items.append((episode, relevant_local))
            next_handoffs.add(episode.id)
            continue

        if episode.publish_status in _UNAVAILABLE_PUBLISH_STATUSES:
            continue

        local_delivery_complete = _has_required_local_media(
            profile,
            audio=audio,
            mp4=mp4,
            hls=hls,
        )
        if profile.use_dw_stream or local_delivery_complete:
            items.append((episode, relevant_local))

    def sort_key(pair: tuple[Episode, Optional[EpisodeMediaDownload]]):
        episode = pair[0]
        value = (
            episode.published_date
            or episode.went_live_date
            or episode.created_at
        )
        return utc_datetime(value)

    items.sort(key=sort_key, reverse=True)
    result = items[:profile.max_items] if profile.max_items > 0 else items

    # A podcast app may keep an older RSS result and call its stable HLS URL
    # after the episode has fallen outside max_items. Keep an established live
    # handoff until the final local HLS artifact exists, independent of feed paging.
    normalized_handoffs = sorted(next_handoffs)
    if list(profile.live_episode_handoff_ids or []) != normalized_handoffs:
        profile.live_episode_handoff_ids = normalized_handoffs

    return result


def get_episode_for_feed(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> Episode:
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
        if not _can_stream_live_episode(s, profile, episode):
            raise HTTPException(
                status_code=404,
                detail="Live episode streaming is not available for this episode",
            )
        return episode

    handoff_active = (
        episode.id in set(profile.live_episode_handoff_ids or [])
        and _profile_keeps_live_handoff(profile)
    )
    downloads: list[EpisodeMediaDownload] | None = None
    resolved_downloads: tuple[
        Optional[EpisodeMediaDownload],
        Optional[EpisodeMediaDownload],
        Optional[EpisodeMediaDownload],
    ] | None = None

    if handoff_active:
        downloads = _episode_downloads(s, profile, episode.id)
        resolved_downloads = _mode_downloads(s, profile, downloads)
        hls = resolved_downloads[2]
        if hls is not None and _download_completes_live_handoff(hls):
            remaining = set(profile.live_episode_handoff_ids or [])
            remaining.discard(episode.id)
            profile.live_episode_handoff_ids = sorted(remaining)
            handoff_active = False
        else:
            return episode

    if episode.publish_status == EpisodePublishStatus.NO_USABLE_MEDIA.value:
        raise HTTPException(status_code=404, detail="Episode has no usable media")
    if episode.publish_status == EpisodePublishStatus.DW_PROCESSING.value:
        raise HTTPException(status_code=404, detail="Episode media is still processing")

    if downloads is None:
        downloads = _episode_downloads(s, profile, episode.id)
    if resolved_downloads is None:
        resolved_downloads = _mode_downloads(s, profile, downloads)
    audio, mp4, hls = resolved_downloads
    if _has_required_local_media(
        profile,
        audio=audio,
        mp4=mp4,
        hls=hls,
    ):
        return episode
    if profile.use_dw_stream:
        return episode

    raise HTTPException(status_code=404, detail="No media available for this episode")


def get_media_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> tuple[Episode, Optional[EpisodeMediaDownload]]:
    """Resolve the profile's primary/representative local media, or remote fallback."""
    episode = get_episode_for_feed(s, profile, episode_slug)
    downloads = _episode_downloads(s, profile, episode.id)
    audio, mp4, hls = _mode_downloads(s, profile, downloads)
    return episode, _relevant_local_download(
        profile,
        audio=audio,
        mp4=mp4,
        hls=hls,
    )


def get_download_for_episode(
        s: Session,
        profile: RssStreamProfile,
        episode_slug: str,
) -> EpisodeMediaDownload:
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
            if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
            else "video"
        )

    media_url = detail.audio_url if media_kind == "audio" else detail.video_url
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


def _append_episode_number_values(
    item: Element,
    *,
    episode_number: int,
    podcast_episode_number: str | None = None,
) -> None:
    if episode_number < 1:
        return
    _sub_text(item, "itunes:episode", str(episode_number))
    _sub_text(
        item,
        "podcast:episode",
        podcast_episode_number or str(episode_number),
    )


def _append_identifier_episode_number(item: Element, episode: Episode) -> None:
    info = episode.episode_identifier_info
    if (
        info.type not in {EpIdType.EP, EpIdType.EP_EXTRA}
        or info.episode_number is None
        or not info.episode_number.isdigit()
    ):
        return

    episode_number = int(info.episode_number)
    podcast_episode_number = str(episode_number)
    if info.sub_episode_number and info.sub_episode_number.isdigit():
        sub_episode_number = int(info.sub_episode_number)
        if sub_episode_number > 0:
            podcast_episode_number = f"{episode_number}.{sub_episode_number}"

    _append_episode_number_values(
        item,
        episode_number=episode_number,
        podcast_episode_number=podcast_episode_number,
    )


def _append_podcast_item_metadata(
        item: Element,
        episode: Episode,
        *,
        identifier_type: str,
) -> None:
    info = episode.episode_identifier_info

    if (
        info.type == EpIdType.TRAILER
        or (
            info.type == EpIdType.EP_EXTRA
            and info.extra_type == EpisodeExtraType.TRAILER
        )
    ):
        episode_type = "trailer"
    elif info.type in {EpIdType.AUX, EpIdType.EP_EXTRA}:
        episode_type = "bonus"
    else:
        episode_type = "full"
    _sub_text(item, "itunes:episodeType", episode_type)

    if identifier_type == EpisodeIdentifier.NUMBERED.value:
        # Numbered identifiers represent a real show-global episode number.
        # Standalone AUX/TRAILER counters are intentionally excluded above.
        if info.season_number is None:
            _append_identifier_episode_number(item, episode)
        return

    if identifier_type != EpisodeIdentifier.SEASONAL.value:
        return

    season = episode.season
    if season is None or season.season_number < 1:
        return

    season_number = int(season.season_number)
    _sub_text(item, "itunes:season", str(season_number))

    podcast_season = SubElement(
        item,
        "podcast:season",
        {"name": season.name},
    )
    podcast_season.text = str(season_number)

    # Only source-backed seasonal identifiers have a real episode number.
    # Standalone auxiliary/trailer counters are show-global WireLoft identifiers
    # and must not be exposed as season episode numbers.
    if info.season_number != season_number:
        return

    _append_identifier_episode_number(item, episode)


def _append_alternate_enclosure(
        item: Element,
        *,
        media_type: str,
        media_url: str,
        title: str,
) -> None:
    alternate = SubElement(
        item,
        "podcast:alternateEnclosure",
        {
            "type": media_type,
            "length": "0",
            "lang": "en",
            "title": title,
            "rel": "alternate",
        },
    )
    SubElement(alternate, "podcast:source", {"uri": media_url})


def _append_item(
        channel: Element,
        *,
        media_base_url: str,
        episode: Episode,
        profile: RssStreamProfile,
) -> None:
    item = SubElement(channel, "item")
    _sub_text(item, "title", episode.title)

    guid = SubElement(item, "guid", {"isPermaLink": "false"})
    guid.text = episode.uuid

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
    audio_url = f"{media_url}/audio.m4a"
    mp4_url = f"{media_url}/video.mp4"
    hls_url = f"{media_url}/video.m3u8"

    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        enclosure_url = audio_url
        enclosure_type = "audio/mp4"
    elif profile.video_output_mode in RSS_AUDIO_PRIMARY_OUTPUT_MODES:
        enclosure_url = audio_url
        enclosure_type = "audio/mp4"
    else:
        enclosure_url = mp4_url
        enclosure_type = "video/mp4"

    SubElement(
        item,
        "enclosure",
        {
            "url": enclosure_url,
            "length": "0",
            "type": enclosure_type,
        },
    )
    _sub_text(item, "link", media_url)

    _append_podcast_item_metadata(
        item,
        episode,
        identifier_type=profile.show.episode_identifier,
    )

    if profile.preferred_format != PreferredFormat.FORMAT_AUDIO_ONLY.value:
        mode = profile.video_output_mode
        if mode == RssVideoOutputMode.AUDIO_MP4.value:
            _append_alternate_enclosure(
                item,
                media_type="video/mp4",
                media_url=mp4_url,
                title="Video",
            )
        elif mode in RSS_HLS_OUTPUT_MODES:
            _append_alternate_enclosure(
                item,
                media_type=_HLS_MIME_TYPE,
                media_url=hls_url,
                title="Adaptive Video",
            )

    _sub_text(
        item,
        "itunes:duration",
        str(int(round(episode.duration))) if episode.duration else "0",
    )

    image_url = (
        episode.thumbnail_square_path
        or episode.thumbnail_landscape_path
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
    effective_title = RssStreamProfileAPIRead.model_validate(profile).effective_title
    items = get_feed_items(s, profile)

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
    _sub_text(channel, "title", effective_title)
    _sub_text(channel, "link", show.sharing_url)
    _sub_text(
        channel,
        "description",
        _escape_bare_html_ampersands(show.description or effective_title),
    )
    _sub_text(channel, "language", "en-us")
    _sub_text(channel, "generator", "WireLoft")
    _sub_text(channel, "itunes:author", show.author_name)
    _sub_text(channel, "itunes:explicit", "false")
    _sub_text(
        channel,
        "itunes:type",
        (
            "episodic"
            if show.type == ShowType.PODCAST.value
            else "serial"
        ),
    )
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
        _sub_text(image, "title", effective_title)
        _sub_text(image, "link", show.sharing_url)

    for episode, _download in items:
        _append_item(
            channel,
            media_base_url=media_base_url,
            episode=episode,
            profile=profile,
        )

    return tostring(rss, encoding="UTF-8", xml_declaration=True)
