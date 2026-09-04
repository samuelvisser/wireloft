from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskResult:
    """Structured terminal output from a worker.

    ``summary`` is suitable for a human-facing completion message. ``data`` is
    machine-readable so UI consumers can present richer, action-specific detail
    without inventing side channels in domain models or task logs.
    """

    summary: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "data": dict(self.data),
        }
