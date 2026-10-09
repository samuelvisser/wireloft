"""Rename the persisted episode download delay setting in config.yml.

Revision ID: b7d2f49c0a13
Revises: 3c8f6a1d2b47
"""

from __future__ import annotations

from pathlib import Path
import os
import stat
import tempfile

import yaml
from yaml.nodes import MappingNode, ScalarNode

from config.registry import reload_settings
from config.settings.base import get_config_path


revision = "b7d2f49c0a13"
down_revision = "3c8f6a1d2b47"
title = "Rename episode download delay configuration"


def _renamed_delay_setting(source: str) -> str:
    """Rename only the targeted YAML key, preserving other text and comments."""
    root = yaml.compose(source)
    if not isinstance(root, MappingNode):
        return source

    for section_key, section_value in root.value:
        if (
            not isinstance(section_key, ScalarNode)
            or section_key.value not in {"downloadSettings", "download_settings"}
            or not isinstance(section_value, MappingNode)
        ):
            continue

        canonical_present = any(
            isinstance(key, ScalarNode)
            and key.value in {"episodeDownloadDelayMinutes", "episode_download_delay_minutes"}
            for key, _ in section_value.value
        )

        for key, value in section_value.value:
            if (
                isinstance(key, ScalarNode)
                and key.value in {
                    "automaticEpisodeDownloadDelayMinutes",
                    "automatic_episode_download_delay_minutes",
                }
            ):
                if canonical_present:
                    # If the new key is also present, preserve its value and
                    # discard the obsolete, single-line scalar setting.
                    line_number = key.start_mark.line
                    if isinstance(value, ScalarNode) and value.end_mark.line == line_number:
                        lines = source.splitlines(keepends=True)
                        del lines[line_number]
                        return "".join(lines)
                    return source

                begin, end = key.start_mark.index, key.end_mark.index
                raw_key = source[begin:end]
                original_name = key.value
                replacement_name = (
                    "episodeDownloadDelayMinutes"
                    if original_name == "automaticEpisodeDownloadDelayMinutes"
                    else "episode_download_delay_minutes"
                )
                return source[:begin] + raw_key.replace(original_name, replacement_name) + source[end:]

    return source


async def migrate(context) -> None:
    context.raise_if_cancelled()
    path = get_config_path()
    try:
        original = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return

    updated = _renamed_delay_setting(original)
    if updated == original:
        return

    # Write into the same directory so replacement is atomic, and preserve
    # the original file mode rather than exposing configuration secrets.
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".wireloft-settings-",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(updated)

        temporary_path.chmod(stat.S_IMODE(path.stat().st_mode))
        context.raise_if_cancelled()
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    # The settings instance was loaded before background migrations started.
    # Install the corrected configuration immediately for active workers/UI.
    reload_settings()
