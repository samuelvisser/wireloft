from backend.api.models.response import HealthResponse


def get_health() -> list[HealthResponse]:
    return [HealthResponse(status="ok")]