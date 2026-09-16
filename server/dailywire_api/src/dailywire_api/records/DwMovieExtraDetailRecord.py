from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .DwCatalogRecord import DwMovieExtraRecord, DwMovieDetailRecord


class DwMovieExtraDetailRecord(DwMovieDetailRecord):
    """Movie-extra playback plus metadata returned by the same ``getClip`` call."""

    metadata: DwMovieExtraRecord

    @classmethod
    def from_clip_payload(
        cls,
        raw: Mapping[str, Any],
        *,
        video_url: str | None,
    ) -> "DwMovieExtraDetailRecord":
        metadata_payload = dict(raw)
        images = raw.get("images")
        if isinstance(images, Mapping):
            thumbnail = images.get("thumbnail")
            if isinstance(thumbnail, Mapping):
                aliases = {
                    "land": "thumbnailLandscapePath",
                    "port": "thumbnailPortraitPath",
                    "square": "thumbnailSquarePath",
                }
                for source_field, target_field in aliases.items():
                    if source_field in thumbnail:
                        metadata_payload[target_field] = thumbnail[source_field]

        return cls(
            video_url=video_url,
            trailer_url=None,
            duration=float(raw.get("duration") or 0),
            trailer_duration=0,
            has_video=bool(video_url),
            metadata=DwMovieExtraRecord.model_validate(metadata_payload),
        )
