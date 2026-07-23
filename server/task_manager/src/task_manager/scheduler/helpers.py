

def is_interval_like_cron(cron_expr: str) -> bool:
    """Heuristic to detect interval-like cron that should run immediately on startup.

    Consider interval-like when only the minutes field is a step (*/N or X/N),
    and other fields are wildcards ("*" or "?").
    """
    parts = [p.strip() for p in cron_expr.split()]
    if len(parts) != 5:
        return False
    minute, hour, day, month, dow = parts

    def _is_wild(s: str) -> bool:
        return s in ("*", "?")

    def _is_step(s: str) -> bool:
        return "/" in s or s.startswith("*/")

    return _is_step(minute) and _is_wild(hour) and _is_wild(day) and _is_wild(month) and _is_wild(dow)