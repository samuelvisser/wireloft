from __future__ import annotations

from collections.abc import Sequence

from backend.db.models import LocalMediaProfileBase
from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


_RENAME_SHOW_FILES_TASK_KEY = "rename_show_profile_files"
_RENAME_MOVIE_FILES_TASK_KEY = "rename_movie_profile_files"
_BULK_DOWNLOAD_TASK_KEY = "media_download_bulk_action_worker"


class LocalMediaProfileFileRenameOperation(OperationDefinition[LocalMediaProfileBase]):
    kind = "local_media_profile.rename_files"
    resource_type = "local_media_profile"

    def __init__(
        self,
        local_media_profile: LocalMediaProfileBase,
        *,
        show_ids: Sequence[int] = (),
        movie_profile: bool = False,
    ) -> None:
        super().__init__(local_media_profile)
        self.show_ids = tuple(dict.fromkeys(int(show_id) for show_id in show_ids))
        self.movie_profile = bool(movie_profile)

    @property
    def title(self) -> str:
        return self.resource.name

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        if self.movie_profile:
            return (
                OperationTargetSpec(
                    task_key=_RENAME_MOVIE_FILES_TASK_KEY,
                    resource_type="local_media_profile",
                    resource_id=self.resource.id,
                    slot_key=f"profile:{self.resource.id}",
                ),
            )
        return tuple(
            OperationTargetSpec(
                task_key=_RENAME_SHOW_FILES_TASK_KEY,
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


class LocalMediaProfileDeleteDownloadsOperation(OperationDefinition[LocalMediaProfileBase]):
    kind = "local_media_profile.delete_downloads"
    resource_type = "local_media_profile"

    def __init__(
        self,
        local_media_profile: LocalMediaProfileBase,
        *,
        media_download_ids: Sequence[int],
        disabled_download_profiles: int,
    ) -> None:
        super().__init__(local_media_profile)
        self.media_download_ids = tuple(
            dict.fromkeys(int(download_id) for download_id in media_download_ids)
        )
        self.disabled_download_profiles = int(disabled_download_profiles)

    @property
    def title(self) -> str:
        return self.resource.name

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_BULK_DOWNLOAD_TASK_KEY,
                resource_type="media_download",
                resource_id=download_id,
                task_kwargs={
                    "media_download_id": download_id,
                    "action": "delete_artifact",
                },
                slot_key=f"media_download:{download_id}",
            )
            for download_id in self.media_download_ids
        )

    def context(self) -> dict[str, object]:
        return {
            "local_media_profile_slug": self.resource.slug,
            "local_media_profile_name": self.resource.name,
            "downloads_requested": len(self.media_download_ids),
            "download_profiles_disabled": self.disabled_download_profiles,
        }
