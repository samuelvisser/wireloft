from typing import Optional

from sqlalchemy.orm import Session


async def run_download_profile_worker(s: Session, *, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    ...