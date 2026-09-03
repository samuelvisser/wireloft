import json
import re
from collections.abc import Iterable


_MANUAL_METADATA_REFRESH_REQUESTS_META_KEY = "manual_metadata_refresh_requests"
_MANUAL_METADATA_REFRESH_REQUEST_LIMIT = 20
_SEASONAL_EPISODE_NUMBER = re.compile(r"^S\d+E(?P<number>\d+)(?:\.\d+)?$")


def episode_type_info(identifier: str | None) -> dict[str, str | None]:
    """Split a WireLoft episode identifier into its type and episode number.

    Seasonal identifiers store both season and episode in the number portion,
    for example ``ep.S01E07``. Normalize those to the actual episode number so
    consumers do not have to understand the seasonal identifier format.
    """
    if not identifier:
        return {"type": None, "number": None}

    episode_type, separator, number = identifier.partition(".")
    if not separator:
        number = None
    elif seasonal_match := _SEASONAL_EPISODE_NUMBER.fullmatch(number):
        number = str(int(seasonal_match.group("number")))

    return {
        "type": episode_type or None,
        "number": number,
    }


def pending_manual_metadata_refresh_request_ids(episode) -> tuple[str, ...]:
    """Return persisted manual metadata-refresh request IDs still awaiting success."""
    raw = episode.get_meta(_MANUAL_METADATA_REFRESH_REQUESTS_META_KEY)
    if not raw:
        return ()

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(parsed, list):
        return ()

    request_ids: list[str] = []
    for value in parsed:
        if isinstance(value, str) and value and value not in request_ids:
            request_ids.append(value)
    return tuple(request_ids)


def add_pending_manual_metadata_refresh_request(episode, request_id: str) -> None:
    """Persist a manual request so restart recovery can retain its correlation ID."""
    request_ids = [
        request_id,
        *(
            existing
            for existing in pending_manual_metadata_refresh_request_ids(episode)
            if existing != request_id
        ),
    ][:_MANUAL_METADATA_REFRESH_REQUEST_LIMIT]
    episode.set_meta(
        _MANUAL_METADATA_REFRESH_REQUESTS_META_KEY,
        json.dumps(request_ids, separators=(",", ":")),
    )


def complete_manual_metadata_refresh_requests(
        episode,
        request_ids: Iterable[str],
) -> None:
    """Remove manual request IDs only after their metadata refresh has succeeded."""
    completed = set(request_ids)
    if not completed:
        return

    remaining = [
        request_id
        for request_id in pending_manual_metadata_refresh_request_ids(episode)
        if request_id not in completed
    ]
    episode.set_meta(
        _MANUAL_METADATA_REFRESH_REQUESTS_META_KEY,
        json.dumps(remaining, separators=(",", ":")),
    )
