"""Telling messages and actions what happened, from the places where it happens.

Each one records the event in the caller's transaction, so it is only sent once that is committed.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode, Show

from .events import Event, emit


def _episode_url(episode: Episode) -> str:
    return f"/show/{episode.show.slug}/episode/{episode.slug}"


def _file_data(episode: Episode, path: str | None) -> dict:
    return {
        "show": episode.show.title, "episode": episode.title, "filePath": path or None,
        "folder": str(Path(path).parent) if path else None,
    }


def episode_downloaded(session: Session, episode: Episode, *, path: str, replaced: bool) -> None:
    """A download finished: a new one, or a better version that replaced the old file."""
    show = episode.show
    emit(
        session, Event.EPISODE_REPLACED if replaced else Event.EPISODE_DOWNLOADED,
        title=f"{'Replaced' if replaced else 'Downloaded'}: {episode.title}", body=show.title,
        show_id=show.id, url=_episode_url(episode), data=_file_data(episode, path),
    )


def episode_deleted(session: Session, episode: Episode, *, path: str | None, reason: str) -> None:
    """A download's file was removed, by hand or because it fell outside its profile's limit."""
    show = episode.show
    emit(
        session, Event.EPISODE_DELETED, title=f"Deleted: {episode.title}", body=f"{show.title}. {reason}",
        show_id=show.id, url=_episode_url(episode), data=_file_data(episode, path),
    )


def new_episodes_found(session: Session, show: Show, count: int) -> None:
    """New episodes in a show that downloads nothing by itself.

    The first look at a new show finds every episode, which is not news.
    """
    if count <= 0:
        return
    downloads = session.scalar(select(DownloadProfileBase.id).where(
        DownloadProfileBase.show_id == show.id, DownloadProfileBase.enable_profile.is_(True),
    ).limit(1))
    if downloads is not None:
        return
    episodes = session.scalar(select(func.count(Episode.id)).where(Episode.show_id == show.id)) or 0
    if episodes <= count:
        return
    emit(
        session, Event.NEW_EPISODES,
        title=f"{count} new episode{'s' if count != 1 else ''} in {show.title}",
        body="Nothing downloads them automatically.", show_id=show.id,
        url=f"/show/{show.slug}", data={"show": show.title},
    )
