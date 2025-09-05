from pydantic import BaseModel

class MediaProfileCreateBody(BaseModel):
    name: str
    outputPathTemplate: str
    preferredFormat: str | None = None
    downloadSeriesImages: bool