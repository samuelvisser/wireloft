from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from task_manager.scheduler.operation_factory import OperationDefinition
from task_manager.scheduler.operations import OperationTargetSpec


@dataclass(frozen=True)
class _SettingsCronResource:
    id: int
    title: str


class _SettingsCronOperation(OperationDefinition[_SettingsCronResource]):
    resource_type = "system"
    title_text: ClassVar[str]

    def __init__(self) -> None:
        super().__init__(_SettingsCronResource(id=0, title=self.title_text))


class _SingleTaskSettingsCronOperation(_SettingsCronOperation):
    task: ClassVar[str]
    target_resource_type: ClassVar[str]

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return (
            OperationTargetSpec(
                task_key=self.task,
                resource_type=self.target_resource_type,
                resource_id=0,
            ),
        )


class FindEpisodesCronOperation(_SingleTaskSettingsCronOperation):
    kind = "system.cron.find_episodes"
    title_text = "Find new episodes"
    task = "fetch_new_episodes"
    target_resource_type = "show"


class MonitorPendingEpisodesCronOperation(_SettingsCronOperation):
    kind = "system.cron.monitor_pending_episodes"
    title_text = "Monitor pending episodes"

    def __init__(self, episode_ids: Sequence[int]) -> None:
        super().__init__()
        self.episode_ids = tuple(dict.fromkeys(int(episode_id) for episode_id in episode_ids))

    def targets(self) -> tuple[OperationTargetSpec, ...]:
        return tuple(
            OperationTargetSpec(
                task_key="monitor_pending_episode",
                resource_type="episode",
                resource_id=episode_id,
                slot_key=f"episode:{episode_id}",
            )
            for episode_id in self.episode_ids
        )

    def context(self) -> dict[str, object]:
        return {"episodes_requested": len(self.episode_ids)}


class MonitorNoUsableMediaCronOperation(_SingleTaskSettingsCronOperation):
    kind = "system.cron.monitor_no_usable_media"
    title_text = "Monitor episodes without usable media"
    task = "monitor_no_usable_media_episode"
    target_resource_type = "show"


class VerifyDownloadsCronOperation(_SingleTaskSettingsCronOperation):
    kind = "system.cron.verify_downloads"
    title_text = "Verify downloads"
    task = "download_profile_worker"
    target_resource_type = "download_profile"


class FileWatcherCronOperation(_SingleTaskSettingsCronOperation):
    kind = "system.cron.file_watcher"
    title_text = "File watcher"
    task = "file_watcher"
    target_resource_type = "show"
