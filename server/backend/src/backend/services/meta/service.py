from flask import jsonify

from backend.app import db_session
from backend.db.models import MediaProfile
from .response_models import MediaProfileItem


@app.get("/api/health")
def health():
    return HealthResponse(status="ok").model_dump()