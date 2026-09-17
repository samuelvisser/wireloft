from __future__ import annotations

import re


_END_RAW_RE = re.compile(r"{%[-]?\s*endraw\s*[-]?%}")


def _statement_keyword(source: str) -> str:
    body = source[2:-2] if source.startswith("{%") and source.endswith("%}") else source
    match = re.match(r"\s*-?\s*([A-Za-z_][A-Za-z0-9_]*)", body)
    return match.group(1) if match else ""


def _find_tag_end(source: str, start: int, end_delimiter: str) -> int:
    if end_delimiter == "#}":
        return source.find(end_delimiter, start + 2)

    quote: str | None = None
    escaped = False
    index = start + 2
    while index < len(source) - 1:
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {"'", '"'}:
            quote = character
            index += 1
            continue

        if source.startswith(end_delimiter, index):
            return index
        index += 1
    return -1


def _next_tag(source: str, cursor: int) -> tuple[int, str, str, str] | None:
    candidates = []
    for start_delimiter, end_delimiter, tag_type in (
        ("{{", "}}", "expression"),
        ("{%", "%}", "statement"),
        ("{#", "#}", "comment"),
    ):
        index = source.find(start_delimiter, cursor)
        if index >= 0:
            candidates.append((index, start_delimiter, end_delimiter, tag_type))
    return min(candidates, default=None, key=lambda candidate: candidate[0])


def normalize_output_template_expression_spacing(output_template: str) -> str:
    """Normalize complete Jinja print expressions to ``{{ expression }}``.

    Statements, comments, raw blocks, incomplete expressions, and Jinja whitespace-control
    expressions are preserved exactly so this normalization cannot change template semantics.
    """
    pieces: list[str] = []
    cursor = 0
    raw = False

    while cursor < len(output_template):
        if raw:
            match = _END_RAW_RE.search(output_template, cursor)
            if not match:
                pieces.append(output_template[cursor:])
                break
            pieces.append(output_template[cursor:match.end()])
            cursor = match.end()
            raw = False
            continue

        next_tag = _next_tag(output_template, cursor)
        if next_tag is None:
            pieces.append(output_template[cursor:])
            break

        start, _start_delimiter, end_delimiter, tag_type = next_tag
        pieces.append(output_template[cursor:start])
        end = _find_tag_end(output_template, start, end_delimiter)
        if end < 0:
            pieces.append(output_template[start:])
            break

        token_end = end + len(end_delimiter)
        token = output_template[start:token_end]
        if tag_type == "expression" and not (token.startswith("{{-") or token.endswith("-}}")):
            body = token[2:-2].strip()
            pieces.append(f"{{{{ {body} }}}}" if body else token)
        else:
            pieces.append(token)

        if tag_type == "statement" and _statement_keyword(token) == "raw":
            raw = True
        cursor = token_end

    return "".join(pieces)
