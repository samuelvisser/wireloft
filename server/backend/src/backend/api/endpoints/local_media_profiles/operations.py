from __future__ import annotations

from collections.abc import Sequence

from backend.db.models import Episode, LocalMediaProfileBase
from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


_RENAME_FILE_TASK_KEY = "rename_file_worker"


class LocalMediaProfileFileRenameOperation(OperationDefinition[LocalMediaProfileBase]):
    kind = "local_media_profile.rename_files"
    resource_type = "local_media_profile"

    def __init__(
        self,
        local_media_profile: LocalMediaProfileBase,
        episodes: Sequence[Episode],
    ) -> None:
        super().__init__(local_media_profile)
        self.episodes = tuple(episodes)

    @property
    def title(self) -> str:
        return self.resource.name

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_RENAME_FILE_TASK_KEY,
                resource_type="episode",
                resource_id=episode.id,
                task_kwargs={"local_media_profile_id": self.resource.id},
                slot_key=f"episode:{episode.id}",
            )
            for episode in self.episodes
        )

    def context(self) -> dict[str, object]:
        return {
            "local_media_profile_slug": self.resource.slug,
            "local_media_profile_name": self.resource.name,
            "episodes_requested": len(self.episodes),
        }
