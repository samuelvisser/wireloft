from __future__ import annotations

from dataclasses import dataclass
import re

from backend.types.download_profile_types import EpIdType
from backend.types.episode_types import EpisodeExtraType


_SEASONAL_EPISODE = re.compile(r"^S(?P<season>\d+)E(?P<number>\d+)$")
_SEASONAL_EPISODE_EXTRA = re.compile(
    r"^S(?P<season>\d+)E(?P<number>\d+)\.(?P<sub_number>\d+)$"
)
_NUMBER = re.compile(r"^\d+$")


@dataclass(frozen=True)
class EpisodeIdentifierInfo:
    """Structured semantics encoded in one canonical WireLoft episode identifier."""

    type: str | None
    extra_type: str | None = None
    season_number: int | None = None
    episode_number: str | None = None
    sub_episode_number: str | None = None
    label: str = ""

    @classmethod
    def from_identifier(cls, identifier: str | None) -> "EpisodeIdentifierInfo":
        if not identifier:
            return cls(type=None)

        if identifier.startswith(f"{EpIdType.EP_EXTRA}."):
            return cls._parse_episode_extra(identifier)

        episode_type, separator, payload = identifier.partition(".")
        if not separator or not payload:
            raise ValueError(f"Invalid WireLoft episode identifier: {identifier!r}")

        if episode_type == EpIdType.EP:
            seasonal = _SEASONAL_EPISODE.fullmatch(payload)
            if seasonal:
                episode_number = str(int(seasonal.group("number")))
                return cls(
                    type=EpIdType.EP,
                    season_number=int(seasonal.group("season")),
                    episode_number=episode_number,
                    label=f"S{int(seasonal.group('season')):02d}E{int(episode_number):02d}",
                )
            return cls(
                type=EpIdType.EP,
                episode_number=str(int(payload)) if _NUMBER.fullmatch(payload) else payload,
                label=payload,
            )

        if episode_type in {
            EpIdType.AUX,
            EpIdType.TRAILER,
            "not-usable",
        }:
            if not _NUMBER.fullmatch(payload):
                raise ValueError(f"Invalid WireLoft episode identifier: {identifier!r}")
            number = str(int(payload))
            return cls(
                type=episode_type,
                episode_number=number,
                label=number,
            )

        raise ValueError(f"Unsupported WireLoft episode identifier type: {episode_type!r}")

    @classmethod
    def _parse_episode_extra(cls, identifier: str) -> "EpisodeIdentifierInfo":
        parts = identifier.split(".")
        if len(parts) < 4:
            raise ValueError(f"Invalid WireLoft episode-extra identifier: {identifier!r}")

        _, extra_type, *payload_parts = parts
        if extra_type not in {
            EpisodeExtraType.OTHER,
            EpisodeExtraType.TRAILER,
        }:
            raise ValueError(
                f"Unsupported WireLoft episode-extra type: {extra_type!r}"
            )

        payload = ".".join(payload_parts)
        seasonal = _SEASONAL_EPISODE_EXTRA.fullmatch(payload)
        if seasonal:
            season_number = int(seasonal.group("season"))
            episode_number = str(int(seasonal.group("number")))
            sub_number = str(int(seasonal.group("sub_number")))
            return cls(
                type=EpIdType.EP_EXTRA,
                extra_type=extra_type,
                season_number=season_number,
                episode_number=episode_number,
                sub_episode_number=sub_number,
                label=(
                    f"S{season_number:02d}E{int(episode_number):02d}.{sub_number}"
                ),
            )

        if len(payload_parts) != 2:
            raise ValueError(f"Invalid WireLoft episode-extra identifier: {identifier!r}")
        episode_number, sub_number = payload_parts
        if not _NUMBER.fullmatch(episode_number) or not _NUMBER.fullmatch(sub_number):
            raise ValueError(f"Invalid WireLoft episode-extra identifier: {identifier!r}")

        episode_number = str(int(episode_number))
        sub_number = str(int(sub_number))
        return cls(
            type=EpIdType.EP_EXTRA,
            extra_type=extra_type,
            episode_number=episode_number,
            sub_episode_number=sub_number,
            label=f"{episode_number}.{sub_number}",
        )

    @property
    def source_slot(self) -> str | None:
        """Return the Daily Wire number slot for a full episode or attached extra.

        The episode-extra subtype is intentionally excluded: an "other" extra and
        a "trailer" extra with the same main/sub number represent one upstream slot.
        """
        if self.type == EpIdType.EP:
            if self.episode_number is None or not _NUMBER.fullmatch(self.episode_number):
                return None
            if self.season_number is not None:
                return f"S{self.season_number:02d}E{int(self.episode_number):02d}.0"
            return f"{int(self.episode_number)}.0"

        if self.type == EpIdType.EP_EXTRA:
            if self.episode_number is None or self.sub_episode_number is None:
                return None
            if self.season_number is not None:
                return (
                    f"S{self.season_number:02d}E{int(self.episode_number):02d}."
                    f"{int(self.sub_episode_number)}"
                )
            return f"{int(self.episode_number)}.{int(self.sub_episode_number)}"

        return None
