import re


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
