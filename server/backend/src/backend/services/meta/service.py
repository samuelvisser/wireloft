from .response_models import HealthResponse


def get_health() -> list[HealthResponse]:
    return [HealthResponse(status="ok")]