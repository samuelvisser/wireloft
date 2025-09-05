from pydantic import BaseModel

class ShowCreateBody(BaseModel):
    url: str
    mediaProfileSlug: str
    name: str
    author: str
    downloadMedia: bool
    downloadDelayMinutes: int | str
    redownloadAfterMinutes: int | str
    downloadDays: int | str
    deleteOlder: bool
    titleFilter: str | None = None