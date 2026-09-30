from __future__ import annotations

from sqlalchemy.orm import Session
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.download_adapter import run_download


async def run_download_movie(
    session: Session, *, media_download_id: int, is_redownload: bool = False, progress=None,
) -> TaskResult:
    return run_download(session, media_download_id=media_download_id, is_redownload=is_redownload, progress=progress)
