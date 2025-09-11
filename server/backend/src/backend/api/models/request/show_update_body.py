from .request_base import RequestModel
from backend.api.models.response import ShowItemResponse


class ShowUpdateBody(ShowItemResponse, RequestModel):
    ...