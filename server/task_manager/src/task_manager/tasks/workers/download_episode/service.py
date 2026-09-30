from __future__ import annotations

from sqlalchemy.orm import Session
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.download_adapter import run_download


async def run_download_episode(
    s: Session, *, media_download_id: int, is_redownload: bool = False,
    prepare_existing_artifact: bool = False, progress=None,
) -> TaskResult:
    return run_download(
        s,
        media_download_id=media_download_id,
        is_redownload=is_redownload,
        prepare_existing_artifact=prepare_existing_artifact,
        progress=progress,
    )
