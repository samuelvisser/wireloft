from pydantic import BaseModel

class MediaProfileUpdateBody(BaseModel):
    name: str | None = None
    outputPathTemplate: str | None = None
    preferredFormat: str | None = None
    downloadSeriesImages: bool | None = None