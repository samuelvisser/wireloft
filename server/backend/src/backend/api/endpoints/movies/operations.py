from __future__ import annotations

from collections.abc import Sequence

from backend.db.models.media_item import Movie
from task_manager.scheduler.operation_factory import OperationDefinition


_REFRESH_MOVIE_EXTRAS_TASK_KEY = "refresh_movie_extras"


class MovieExtrasRefreshOperation(OperationDefinition[Movie]):
    kind = "movie.refresh_extras"
    resource_type = "movie"
    task = _REFRESH_MOVIE_EXTRAS_TASK_KEY

    def context(self) -> dict[str, object]:
        return {
            "movie_slug": self.resource.slug,
            "movie_title": self.resource.title,
        }


class MovieRedownloadOperation(OperationDefinition[Movie]):
    kind = "movie.redownload_media"
    resource_type = "movie"

    def __init__(self, movie: Movie, *, media_download_ids: Sequence[int]) -> None:
        super().__init__(movie)
        self.media_download_ids = tuple(
            dict.fromkeys(int(download_id) for download_id in media_download_ids)
        )

    def context(self) -> dict[str, object]:
        return {
            "movie_slug": self.resource.slug,
            "movie_title": self.resource.title,
            "downloads_requested": len(self.media_download_ids),
        }
