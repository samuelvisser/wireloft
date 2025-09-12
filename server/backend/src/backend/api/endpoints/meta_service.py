from backend.api.models.meta import HealthAPIRead


def get_health() -> HealthAPIRead:
    return HealthAPIRead(status="ok")