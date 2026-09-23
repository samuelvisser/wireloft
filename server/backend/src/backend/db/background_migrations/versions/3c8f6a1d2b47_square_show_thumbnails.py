"""Populate show square thumbnails from The Daily Wire Watch page.

Revision ID: 3c8f6a1d2b47
Revises: f6a1c3d8b427
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from backend.db.core import get_session
from backend.db.models import Show
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_authorisation import DeviceAuthClient


revision = "3c8f6a1d2b47"
down_revision = "f6a1c3d8b427"
title = "Populate show square thumbnails from The Daily Wire"


def _show_count() -> int:
    session = get_session()
    try:
        return int(session.scalar(select(func.count(Show.id))) or 0)
    finally:
        session.close()


def _apply_square_thumbnails(thumbnails: dict[str, str]) -> int:
    """Apply only artwork present in the carousel; absent shows are expected."""
    session = get_session()
    updated = 0
    try:
        for show in session.scalars(select(Show).order_by(Show.id)):
            if show.thumbnail_square_path is not None:
                continue

            square_path = thumbnails.get(show.slug)
            if square_path is None:
                continue

            show.thumbnail_square_path = square_path
            updated += 1
        session.commit()
        return updated
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def migrate(context) -> None:
    show_count = _show_count()
    if show_count == 0:
        return

    context.raise_if_cancelled()
    context.update_progress(
        0,
        show_count,
        "Fetching square show thumbnails from The Daily Wire",
    )

    tokens = await asyncio.to_thread(DeviceAuthClient().get_token)
    client = MiddlewareClient(
        access_token=tokens.access_token if tokens else None,
    )
    thumbnails = await asyncio.to_thread(client.get_square_show_thumbnails)

    context.raise_if_cancelled()
    _apply_square_thumbnails(thumbnails)

    context.update_progress(
        show_count,
        show_count,
        "Updated square show thumbnails",
    )
