from __future__ import annotations

from collections.abc import Sequence

from backend.db.models import LocalMediaProfileBase
from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


_RENAME_FILES_TASK_KEY = "rename_show_profile_files"


class LocalMediaProfileFileRenameOperation(OperationDefinition[LocalMediaProfileBase]):
    kind = "local_media_profile.rename_files"
    resource_type = "local_media_profile"

    def __init__(
        self,
        local_media_profile: LocalMediaProfileBase,
        show_ids: Sequence[int],
    ) -> None:
        super().__init__(local_media_profile)
        self.show_ids = tuple(dict.fromkeys(int(show_id) for show_id in show_ids))

    @property
    def title(self) -> str:
        return self.resource.name

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_RENAME_FILES_TASK_KEY,
                resource_type="show",
                resource_id=show_id,
                task_kwargs={"local_media_profile_id": self.resource.id},
                slot_key=f"show:{show_id}",
            )
            for show_id in self.show_ids
        )

    def context(self) -> dict[str, object]:
        return {
            "local_media_profile_slug": self.resource.slug,
            "local_media_profile_name": self.resource.name,
            "shows_requested": len(self.show_ids),
        }
