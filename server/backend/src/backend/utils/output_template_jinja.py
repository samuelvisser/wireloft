from __future__ import annotations

import re
from collections.abc import Callable

from jinja2 import StrictUndefined, pass_context
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


def create_output_template_environment(
    *,
    custom_index_resolver: Callable[[str], object] | None = None,
) -> ImmutableSandboxedEnvironment:
    """Create WireLoft's isolated sandbox for Local Media Profile path templates."""
    environment = ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # Path templates only need explicitly supplied media values. Removing globals
    # also keeps helpers such as range() unavailable to user templates.
    environment.globals.clear()
    @pass_context
    def custom_index(_context, value: object) -> object:
        # custom_index is deliberately context-dependent. Marking it this way
        # prevents Jinja from constant-folding literal filter calls while
        # compiling the template, which would otherwise evaluate dead branches
        # and allocate indexes that the rendered path never reaches.
        if custom_index_resolver is None:
            return ""
        return custom_index_resolver(str(value))

    environment.filters.update({
        "regex_replace": regex_replace,
        "regex_search": regex_search,
        "custom_index": custom_index,
    })
    return environment
