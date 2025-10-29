from typing import Optional

from sqlalchemy.orm import Session


async def run_monitor_episode_worker(s: Session, *, episode_id: Optional[int] = None, episode_slug: Optional[str] = None) -> None:
    print("Starting monitor_episode_worker")
    ...