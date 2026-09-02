"""Migrate filename restriction setting.

Revision ID: b7c3f1a9d2e4
Revises: a1d4e7f2c9b6
Create Date: 2026-09-02

"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Sequence, Union

from config.settings.base import get_config_path


revision: str = "b7c3f1a9d2e4"
down_revision: Union[str, None] = "a1d4e7f2c9b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOWNLOAD_SETTINGS_SECTION = re.compile(
    r"^(?P<indent>\s*)(?:downloadSettings|download_settings)\s*:\s*(?:#.*)?$"
)
_LEGACY_SETTING = re.compile(
    r"^(?P<indent>\s*)(?:asciiOnlyFilenames|ascii_only_filenames)\s*:"
)
_CURRENT_SETTING = re.compile(
    r"^(?P<indent>\s*)(?:filenameRestrictionMode|filename_restriction_mode)\s*:"
)


def _find_download_setting_lines(text: str) -> tuple[list[str], list[int], list[int]]:
    lines = text.splitlines(keepends=True)
    section_indent: int | None = None
    legacy_indexes: list[int] = []
    current_indexes: list[int] = []

    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(content) - len(content.lstrip())
        if section_indent is None:
            section = _DOWNLOAD_SETTINGS_SECTION.match(content)
            if section:
                section_indent = len(section.group("indent"))
            continue

        if indent <= section_indent:
            break
        if _LEGACY_SETTING.match(content):
            legacy_indexes.append(index)
        elif _CURRENT_SETTING.match(content):
            current_indexes.append(index)

    return lines, legacy_indexes, current_indexes


def _replace_line(line: str, *, key: str, value: str) -> str:
    content = line.rstrip("\r\n")
    newline = line[len(content):]
    indent = content[:len(content) - len(content.lstrip())]
    return f"{indent}{key}: {value}{newline}"


def _upgrade_config_text(text: str) -> str:
    lines, legacy_indexes, current_indexes = _find_download_setting_lines(text)
    if not legacy_indexes:
        return text

    if current_indexes:
        for index in reversed(legacy_indexes):
            del lines[index]
        return "".join(lines)

    first = legacy_indexes[0]
    lines[first] = _replace_line(
        lines[first],
        key="filenameRestrictionMode",
        value="windows",
    )
    for index in reversed(legacy_indexes[1:]):
        del lines[index]
    return "".join(lines)


def _downgrade_config_text(text: str) -> str:
    lines, legacy_indexes, current_indexes = _find_download_setting_lines(text)
    if legacy_indexes or not current_indexes:
        return text

    first = current_indexes[0]
    lines[first] = _replace_line(
        lines[first],
        key="asciiOnlyFilenames",
        value="true",
    )
    for index in reversed(current_indexes[1:]):
        del lines[index]
    return "".join(lines)


def _write_if_changed(path: Path, original: str, updated: str) -> None:
    if updated == original:
        return

    file_mode = path.stat().st_mode & 0o777
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.write(updated)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, file_mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _migrate_config(transform) -> None:
    path = get_config_path()
    try:
        original = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    _write_if_changed(path, original, transform(original))


def upgrade() -> None:
    # Both legacy boolean values intentionally migrate to the new Windows mode.
    _migrate_config(_upgrade_config_text)


def downgrade() -> None:
    # The old setting cannot represent all three new modes; restore its old default.
    _migrate_config(_downgrade_config_text)
