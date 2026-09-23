from __future__ import annotations

from typing import Literal, Protocol, TypeVar


ThumbnailOrientation = Literal["landscape", "portrait", "square"]

_THUMBNAIL_FIELDS: dict[ThumbnailOrientation, str] = {
    "landscape": "thumbnail_landscape_path",
    "portrait": "thumbnail_portrait_path",
    "square": "thumbnail_square_path",
}


class ThumbnailRecord(Protocol):
    thumbnail_landscape_path: str | None
    thumbnail_portrait_path: str | None
    thumbnail_square_path: str | None


ThumbnailRecordT = TypeVar("ThumbnailRecordT", bound=ThumbnailRecord)


def normalize_thumbnail_aliases(
    record: ThumbnailRecordT,
    *,
    default: ThumbnailOrientation,
) -> ThumbnailRecordT:
    """Remove thumbnail slots that only duplicate the media type's default.

    The Daily Wire sometimes puts the same image URL in several orientation
    fields. Keep the default orientation as the authoritative slot and clear an
    alternate only when its URL is exactly identical. Distinct URLs are always
    preserved so newly supported upstream orientations work automatically.
    """
    default_field = _THUMBNAIL_FIELDS[default]
    default_path = getattr(record, default_field)
    if not default_path:
        return record

    for orientation, field in _THUMBNAIL_FIELDS.items():
        if orientation == default:
            continue
        if getattr(record, field) == default_path:
            object.__setattr__(record, field, None)

    return record
