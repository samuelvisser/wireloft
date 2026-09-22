from __future__ import annotations

from backend.db.models import Show


class ShowAdded(dict[str, object]):
    """Canonical payload for the ``show.added`` domain event."""

    def __init__(self, show: Show) -> None:
        super().__init__(
            resource_id=show.id,
            id=show.id,
            slug=show.slug,
            title=show.title,
            # Match ShowIndexOperation.task_kwargs so the event-triggered run can
            # satisfy the durable operation target.
            initial_index=True,
        )
