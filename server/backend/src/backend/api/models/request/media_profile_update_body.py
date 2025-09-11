from .request_base import RequestModel
from backend.api.models.response import MediaProfileItemResponse


class MediaProfileUpdateBody(MediaProfileItemResponse, RequestModel):
    ...