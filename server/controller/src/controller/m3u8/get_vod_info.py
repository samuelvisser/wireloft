from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import re

STREAM_INF = "#EXT-X-STREAM-INF"
EXTINF_RE = re.compile(r"#EXTINF:([0-9.]+)")
PART_DUR_RE = re.compile(r"DURATION=([0-9.]+)")  # for #EXT-X-PART
CODEC_VIDEO_HINTS = ("avc1", "hvc", "hev1", "vp9", "av01")  # typical video codec tags


@dataclass
class HlsInfo:
    playlist_type: str  # VOD | EVENT | LIVE
    seconds: Decimal
    segments: int
    variant_url: str


def _fetch_text(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> tuple[str, str]:
    """Fetch URL and return (text, final_url after redirects)."""
    req = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        body = resp.read().decode(charset, errors="replace")
        return body, resp.geturl()


def _split_attr_list(s: str) -> list[str]:
    """Split an HLS attribute list (key=value pairs) on commas outside quotes."""
    parts, cur, in_q = [], [], False
    for ch in s:
        if ch == '"':
            in_q = not in_q
            cur.append(ch)
        elif ch == ',' and not in_q:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def _parse_attr_list(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for kv in _split_attr_list(s):
        if '=' not in kv:
            continue
        k, v = kv.split('=', 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _pick_variant(master_text: str, base_url: str) -> str | None:
    """
    Pick a rendition from a master playlist. Prefer highest-bandwidth *video* variant.
    Fall back to highest-bandwidth of any type if no explicit video codecs found.
    """
    lines = [ln.strip() for ln in master_text.splitlines() if ln.strip()]
    best_video: tuple[int, str] | None = None  # (bandwidth, uri)
    best_any: tuple[int, str] | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(STREAM_INF):
            attr = _parse_attr_list(line[len(STREAM_INF) + 1 :])
            # the next non-tag line is the URI
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            if j < len(lines):
                uri = urljoin(base_url, lines[j])
                bw = int(attr.get("BANDWIDTH", "0") or "0")
                codecs = (attr.get("CODECS") or "").lower()
                is_video = any(hint in codecs for hint in CODEC_VIDEO_HINTS)
                cand = (bw, uri)
                if is_video and (best_video is None or bw > best_video[0]):
                    best_video = cand
                if best_any is None or bw > best_any[0]:
                    best_any = cand
            i = j
        else:
            i += 1

    chosen = best_video or best_any
    return chosen[1] if chosen else None


def _parse_media_playlist(text: str) -> tuple[str, Decimal, int]:
    """
    Sum durations of #EXTINF and LL-HLS #EXT-X-PART. Detect VOD/EVENT/LIVE from tags.
    Returns (playlist_type, total_seconds, segment_count).
    """
    total = Decimal("0")
    segs = 0
    playlist_type = "LIVE"
    saw_endlist = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-PLAYLIST-TYPE:VOD"):
            playlist_type = "VOD"
        elif line.startswith("#EXT-X-PLAYLIST-TYPE:EVENT"):
            playlist_type = "EVENT"
        elif line.startswith("#EXT-X-ENDLIST"):
            saw_endlist = True

        m = EXTINF_RE.match(line)
        if m:
            total += Decimal(m.group(1))
            segs += 1
            continue

        if line.startswith("#EXT-X-PART:"):
            pm = PART_DUR_RE.search(line)
            if pm:
                total += Decimal(pm.group(1))

    if playlist_type == "LIVE" and saw_endlist:
        playlist_type = "VOD"
    return playlist_type, total, segs


def get_vod_info(master_url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> HlsInfo:
    """
    Resolve a master playlist to a rendition and compute total duration.
    Works for VOD and will still return a number for EVENT/LIVE (the current window).
    """
    master_text, resolved_master = _fetch_text(master_url, headers=headers, timeout=timeout)

    # If it's already a media playlist, parse directly.
    if STREAM_INF not in master_text:
        ptype, total, segs = _parse_media_playlist(master_text)
        return HlsInfo(ptype, total, segs, resolved_master)

    # Otherwise, pick a variant and parse its media playlist.
    variant_url = _pick_variant(master_text, base_url=resolved_master)
    if not variant_url:
        raise RuntimeError("No variant URI found in the master playlist.")
    media_text, resolved_media = _fetch_text(variant_url, headers=headers, timeout=timeout)
    ptype, total, segs = _parse_media_playlist(media_text)
    return HlsInfo(ptype, total, segs, resolved_media)


def _fmt_hhmmss(total_seconds: Decimal) -> str:
    secs = int(total_seconds)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"