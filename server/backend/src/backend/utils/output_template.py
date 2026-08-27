from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from config import get_settings

if TYPE_CHECKING:
    from backend.db.models import Episode

_DOWNLOADS_PREFIX = "/downloads/"
# Characters that may not appear in a single path component
_UNSAFE_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_path_component(value: str) -> str:
    """Make a template substitution safe to use as one path component."""
    cleaned = _UNSAFE_COMPONENT_CHARS.sub("_", value).strip(" .")
    return cleaned or "_"


def resolve_episode_output_path(
        output_template: str,
        *,
        episode: "Episode",
        extension: Optional[str] = None,
) -> Path:
    """Resolve a Local Media Profile output template to an absolute file path.

    Supported placeholders: ``{show}``/``{show_title}``, ``{season}``/``{season_name}``,
    ``{episode}``/``{episode_title}``/``{title}`` and ``{ep_id}``. The mandatory
    ``/downloads/`` prefix maps to the configured ``download_settings.download_root``
    directory, and the mandatory ``.ext`` suffix is replaced with the actual file
    extension once it is known.
    """
    substitutions = {
        "show": episode.show.slug,
        "show_title": episode.show.title,
        "season": episode.season.slug if episode.season else "",
        "season_name": episode.season.name if episode.season else "",
        "episode": episode.slug,
        "episode_title": episode.title,
        "title": episode.title,
        "ep_id": episode.episode_identifier,
    }

    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace("{" + key + "}", sanitize_path_component(str(value)))

    if resolved.startswith(_DOWNLOADS_PREFIX):
        resolved = resolved[len(_DOWNLOADS_PREFIX):]
    resolved = resolved.lstrip("/")

    if extension is not None and resolved.endswith(".ext"):
        resolved = resolved[: -len("ext")] + extension.lstrip(".")

    root = Path(get_settings().download_settings.download_root)
    return (root / resolved).resolve()
