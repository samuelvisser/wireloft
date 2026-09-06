from __future__ import annotations

from collections.abc import Sequence

from backend.db.models import Episode, Show
from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


_FETCH_EPISODES_TASK_KEY = "fetch_new_episodes"
_REFRESH_METADATA_TASK_KEY = "refresh_episode_metadata_worker"
_RENAME_FILE_TASK_KEY = "rename_file_worker"
_REDOWNLOAD_TASK_KEY = "redownload_show_episodes_worker"


class _ShowOperation(OperationDefinition[Show]):
    resource_type = "show"

    def context(self) -> dict[str, object]:
        return {
            "show_slug": self.resource.slug,
            "show_title": self.resource.title,
        }


class ShowIndexOperation(_ShowOperation):
    kind = "show.index"
    task = _FETCH_EPISODES_TASK_KEY


class ShowSyncOperation(_ShowOperation):
    kind = "show.sync"
    task = _FETCH_EPISODES_TASK_KEY


class ShowMetadataRefreshOperation(_ShowOperation):
    kind = "show.refresh_metadata"

    def __init__(self, show: Show, episodes: Sequence[Episode]) -> None:
        super().__init__(show)
        self.episodes = tuple(episodes)

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_REFRESH_METADATA_TASK_KEY,
                resource_type="episode",
                resource_id=episode.id,
                task_kwargs={"refresh": True},
                slot_key=f"episode:{episode.id}",
            )
            for episode in self.episodes
        )

    def context(self) -> dict[str, object]:
        return {
            **super().context(),
            "episodes_requested": len(self.episodes),
        }


class ShowFileRenameOperation(_ShowOperation):
    kind = "show.rename_files"

    def __init__(
        self,
        show: Show,
        episodes: Sequence[Episode],
        *,
        local_media_profile_id: int | None,
        selected_profile_count: int,
    ) -> None:
        super().__init__(show)
        self.episodes = tuple(episodes)
        self.local_media_profile_id = local_media_profile_id
        self.selected_profile_count = selected_profile_count

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_RENAME_FILE_TASK_KEY,
                resource_type="episode",
                resource_id=episode.id,
                task_kwargs={"local_media_profile_id": self.local_media_profile_id},
                slot_key=f"episode:{episode.id}",
            )
            for episode in self.episodes
        )

    def context(self) -> dict[str, object]:
        return {
            **super().context(),
            "episodes_requested": len(self.episodes),
            "local_media_profiles_requested": self.selected_profile_count,
        }


class ShowRedownloadOperation(_ShowOperation):
    kind = "show.redownload_episodes"
    task = _REDOWNLOAD_TASK_KEY

    def __init__(
        self,
        show: Show,
        *,
        local_media_profile_id: int | None,
        selected_profile_count: int,
    ) -> None:
        super().__init__(show)
        self.local_media_profile_id = local_media_profile_id
        self.selected_profile_count = selected_profile_count

    def task_kwargs(self) -> dict[str, object]:
        return {"local_media_profile_id": self.local_media_profile_id}

    def context(self) -> dict[str, object]:
        return {
            **super().context(),
            "local_media_profiles_requested": self.selected_profile_count,
        }
