from pydantic import BaseModel


class ShowUpdateBody(BaseModel):
    url: str | None = None
    mediaProfileSlug: str | None = None
    name: str | None = None
    author: str | None = None
    downloadMedia: bool | None = None
    downloadDelayMinutes: int | str | None = None
    redownloadAfterMinutes: int | str | None = None
    downloadDays: int | str | None = None
    deleteOlder: bool | None = None
    titleFilter: str | None = None