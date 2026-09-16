from __future__ import annotations


def select_thumbnail_url(media) -> str | None:
    """Choose the best artwork source for embedding or a per-media sidecar."""
    for attribute in (
        "thumbnail_square_path",
        "thumbnail_portrait_path",
        "thumbnail_landscape_path",
        "background_image_path",
    ):
        value = getattr(media, attribute, None)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None
