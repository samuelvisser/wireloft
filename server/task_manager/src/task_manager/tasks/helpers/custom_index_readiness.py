from __future__ import annotations

import asyncio
import fcntl
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic

from sqlalchemy import select

from backend.db.models import CustomIndexState, ShowLocalMediaProfile
from backend.services.custom_indexes import (
    profile_uses_custom_indexes, request_custom_index_reconciliation,
)
from backend.utils.custom_index import CustomIndexNotReadyError
from controller.db_utils import db_session
from config import get_settings


@asynccontextmanager
async def custom_index_pair_lock(
    show_id: int,
    local_media_profile_id: int,
    *,
    shared: bool = False,
):
    """Coordinate filesystem/index work for one Show/Profile pair across workers.

    Maintenance jobs take the default exclusive lock because they mutate index
    assignments or move existing files. Downloads only need a stable generation
    while they resolve and publish their own artifact, so they take a shared lock.
    That keeps maintenance out while still allowing separate downloads for the
    same Show/Profile pair to use the configured global concurrency.
    """
    root = Path(get_settings().download_settings.download_root) / ".wireloft-index-locks"
    root.mkdir(parents=True, exist_ok=True)
    lock_file = (root / f"{show_id}-{local_media_profile_id}.lock").open("a+b")
    lock_mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), lock_mode | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(0.25)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def pair_is_ready(show_id: int, local_media_profile_id: int) -> bool:
    with db_session() as session:
        profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
        if profile is None or not profile_uses_custom_indexes(profile):
            return True
        state = session.scalar(select(CustomIndexState).where(
            CustomIndexState.show_id == show_id,
            CustomIndexState.local_media_profile_id == local_media_profile_id,
        ))
        return state is not None and state.completed_generation == state.requested_generation


def request_missing_index_repair(error: CustomIndexNotReadyError) -> None:
    if error.repair_show_id is None or error.repair_profile_id is None:
        return
    with db_session() as session:
        request_custom_index_reconciliation(
            session, show_id=error.repair_show_id,
            local_media_profile_id=error.repair_profile_id,
        )
        session.commit()


async def wait_for_custom_index_pair(
    show_id: int, local_media_profile_id: int, *, timeout: float = 180,
) -> None:
    """Wait outside the caller's write transaction for the latest generation."""
    deadline = monotonic() + timeout
    while True:
        with db_session() as session:
            profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
            if profile is None or not profile_uses_custom_indexes(profile):
                return
            state = session.scalar(select(CustomIndexState).where(
                CustomIndexState.show_id == show_id,
                CustomIndexState.local_media_profile_id == local_media_profile_id,
            ))
            if state is None:
                request_custom_index_reconciliation(
                    session, show_id=show_id,
                    local_media_profile_id=local_media_profile_id,
                )
                session.commit()
            elif state.completed_generation == state.requested_generation:
                return
        if monotonic() >= deadline:
            raise CustomIndexNotReadyError(
                f"Manage Custom Indexes did not finish for Show {show_id}, "
                f"Local Media Profile {local_media_profile_id}"
            )
        await asyncio.sleep(0.5)
