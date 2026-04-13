from typing import Optional

from sqlalchemy.orm import Session



async def run_file_watcher(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    print("Starting file_watcher")
    ...
    print("file_watcher completed")
