from __future__ import annotations

from collections.abc import Sequence

from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


_BULK_ACTION_TASK_KEY = "media_download_bulk_action_worker"


class _BulkMediaDownloadOperation(OperationDefinition[None]):
    resource_type = "media_download"
    action: str

    def __init__(self, media_download_ids: Sequence[int]) -> None:
        super().__init__(None)
        self.media_download_ids = tuple(dict.fromkeys(media_download_ids))

    @property
    def title(self) -> str:
        return "Downloads"

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key=_BULK_ACTION_TASK_KEY,
                resource_type=self.resource_type,
                resource_id=None,
                task_kwargs={
                    "media_download_id": media_download_id,
                    "action": self.action,
                },
                slot_key=f"media_download:{media_download_id}",
            )
            for media_download_id in self.media_download_ids
        )

    def context(self) -> dict[str, object]:
        return {"downloads_requested": len(self.media_download_ids)}


class BulkRetryMediaDownloadsOperation(_BulkMediaDownloadOperation):
    kind = "media_download.bulk_retry"
    action = "retry"


class BulkCancelMediaDownloadsOperation(_BulkMediaDownloadOperation):
    kind = "media_download.bulk_cancel"
    action = "cancel"
