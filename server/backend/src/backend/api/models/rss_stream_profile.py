from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.download_profile_types import EpIdType
from backend.types.local_media_profile_types import PreferredFormat
from backend.types.stream_profile_types import (
    RSS_HLS_OUTPUT_MODES,
    RssVideoOutputMode,
    StreamProfileType,
)


def _default_episode_types() -> list[EpIdType]:
    return [EpIdType.EP, EpIdType.AUX]


# ---------- Strict input (create/update) ----------
class _RssStreamProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate here (constraints allowed)."""

    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str = Field(min_length=1)
    require_exact_match: bool
    ep_id_type_list: list[EpIdType] = Field(default_factory=_default_episode_types)
    video_output_mode: Optional[RssVideoOutputMode] = Field(
        default_factory=lambda data: (
            None
            if data.get("preferred_format") == PreferredFormat.FORMAT_AUDIO_ONLY.value
            else RssVideoOutputMode.AUDIO_HLS
        )
    )
    stream_live_episodes: bool = False
    max_items: int = Field(default=0, ge=0)

    @field_validator("preferred_format")
    @classmethod
    def _stream_preferred_format_must_be_playback_media(cls, value: str) -> str:
        if value == PreferredFormat.FORMAT_HLS:
            raise ValueError(
                "HLS is a Local Media Profile download format, not a Stream Profile preferred format"
            )
        return value

    @model_validator(mode="after")
    def _validate_video_output(self):
        audio_only = self.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value

        if audio_only and self.video_output_mode is not None:
            raise ValueError(
                "Audio-only Stream Profiles cannot have a video output mode"
            )
        if not audio_only and self.video_output_mode is None:
            raise ValueError(
                "Video Stream Profiles require a video output mode"
            )

        if self.stream_live_episodes and audio_only:
            raise ValueError(
                "Live episode streaming requires a video preferred format"
            )
        if (
            self.stream_live_episodes
            and self.video_output_mode not in RSS_HLS_OUTPUT_MODES
        ):
            raise ValueError(
                "Live episode streaming requires an HLS video podcast output mode"
            )
        return self


class RssStreamProfileAPICreate(_RssStreamProfileAPIBaseIn):
    """Request body for creating an RSS stream profile.

    ``feed_url`` is optional: leave it unset (or blank) to have WireLoft
    generate one automatically from the request host and the profile's
    secret token. It can always be edited afterwards.
    """

    show_id: int
    feed_url: Optional[str] = None


class RssStreamProfileAPIUpdate(_RssStreamProfileAPIBaseIn):
    """Request body for updating an RSS stream profile."""

    feed_url: str = Field(min_length=1)


# ---------- Lenient output (read) ----------
class _RssStreamProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    type: Literal["rss"] = StreamProfileType.RSS.value

    id: int
    show_id: int
    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str
    require_exact_match: bool
    ep_id_type_list: list[str]
    video_output_mode: Optional[str]
    stream_live_episodes: bool
    max_items: int
    feed_url: str


class RssStreamProfileAPIRead(_RssStreamProfileAPIBaseOut):
    """Response body for an RSS stream profile."""

    created_at: datetime
    updated_at: datetime
