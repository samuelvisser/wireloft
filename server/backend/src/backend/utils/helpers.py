import uuid

def slugify(text: str | None) -> str:
    if not text:
        return ""
    s = str(text).strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        elif ch.isspace() or ch in "/\\":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")

def generate_uuid() -> str:
    """
    Generate a new random UUID (v4) as a string.
    """
    return str(uuid.uuid4())