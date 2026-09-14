from __future__ import annotations

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
