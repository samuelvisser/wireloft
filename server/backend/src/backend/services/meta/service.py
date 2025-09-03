from .response_models import HealthResponse


def health():
    return HealthResponse(status="ok").model_dump()