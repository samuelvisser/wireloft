# Known acronym segments to preserve in uppercase when generating camelCase
ACRONYM_PARTS = {
    "id",
    "url",
    "api",
    "html",
    "xml",
    "ip",
    "uuid",
    "ssn",
    "tv",
    "dvd",
    "ui",
    "os",
}

def to_camel_with_acronyms(name: str) -> str:
    """
    Convert snake_case to camelCase and keep common acronyms uppercase.

    Examples:
      - "media_type" -> "mediaType"
      - "background_image" -> "backgroundImage"
      - "sharing_url" -> "sharingURL"
      - "parent_title" -> "parentTitle"
      - "published_at" -> "publishedAt"
    """
    if not isinstance(name, str) or not name:
        return name

    parts = name.split("_")
    first = parts[0]
    rest = []
    for token in parts[1:]:
        if token in ACRONYM_PARTS:
            rest.append(token.upper())
        else:
            rest.append(token[:1].upper() + token[1:])

    return first + "".join(rest)
