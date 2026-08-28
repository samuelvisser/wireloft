def episode_type_info(identifier: str | None) -> dict[str, str | None]:
    """Splits an episode_identifier like 'ep.4232' or 'ep-extra.101.2' into its type and number."""
    if not identifier:
        return {"type": None, "number": None}

    episode_type, separator, number = identifier.partition(".")

    return {
        "type": episode_type or None,
        "number": number if separator else None,
    }