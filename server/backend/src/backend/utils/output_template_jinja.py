from __future__ import annotations

import re
from datetime import date, datetime, time

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateRuntimeError
from jinja2.sandbox import ImmutableSandboxedEnvironment


def _compile_regex(pattern: object) -> re.Pattern[str]:
    try:
        return re.compile(str(pattern))
    except re.error as exc:
        raise TemplateRuntimeError(f"Invalid regular expression: {exc}") from exc


def regex_replace(
    value: object,
    pattern: object,
    replacement: object,
    count: int = 0,
) -> str:
    """Replace regex matches in a Jinja value; count=0 replaces every match."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TemplateRuntimeError("regex_replace count must be a non-negative integer")

    regex = _compile_regex(pattern)
    try:
        return regex.sub(str(replacement), str(value), count=count)
    except re.error as exc:
        raise TemplateRuntimeError(f"Invalid regular expression replacement: {exc}") from exc


def regex_search(value: object, pattern: object) -> bool:
    """Return whether a regex matches anywhere in a Jinja value."""
    return _compile_regex(pattern).search(str(value)) is not None


def _parse_strftime_value(value: object) -> date | datetime | time | None:
    """Parse the canonical date/time strings exposed to output templates."""
    if isinstance(value, (datetime, date, time)):
        return value

    text = str(value)
    if not text:
        return None

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return time.fromisoformat(text)
    except ValueError:
        pass

    # Filename sanitization runs before Jinja. Under the Windows and restricted
    # modes it replaces the colons in canonical time values with underscores.
    datetime_match = re.fullmatch(
        r"(?P<date>\d{4}-\d{2}-\d{2})[ _T]"
        r"(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2}(?:\.\d+)?)",
        text,
    )
    if datetime_match:
        return datetime.fromisoformat(
            f"{datetime_match.group('date')}T"
            f"{datetime_match.group('hour')}:{datetime_match.group('minute')}:"
            f"{datetime_match.group('second')}"
        )

    time_match = re.fullmatch(
        r"(?P<hour>\d{2})_(?P<minute>\d{2})_(?P<second>\d{2}(?:\.\d+)?)",
        text,
    )
    if time_match:
        return time.fromisoformat(
            f"{time_match.group('hour')}:{time_match.group('minute')}:"
            f"{time_match.group('second')}"
        )

    raise TemplateRuntimeError(
        "strftime requires a WireLoft date/time value in ISO format"
    )


def strftime(value: object, format_string: object) -> str:
    """Format a WireLoft date/time value with Python strftime directives."""
    parsed = _parse_strftime_value(value)
    if parsed is None:
        return ""

    try:
        return parsed.strftime(str(format_string))
    except (TypeError, ValueError, OSError) as exc:
        raise TemplateRuntimeError(f"Invalid strftime format: {exc}") from exc


def create_output_template_environment() -> ImmutableSandboxedEnvironment:
    """Create WireLoft's isolated sandbox for Local Media Profile path templates."""
    environment = ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # Path templates only need explicitly supplied media values. Removing globals
    # also keeps helpers such as range() unavailable to user templates.
    environment.globals.clear()
    environment.filters.update({
        "regex_replace": regex_replace,
        "regex_search": regex_search,
        "strftime": strftime,
    })
    return environment
