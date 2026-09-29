from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class ProgressBounds:
    """Closed integer interval used for mapping work -> progress percentage."""
    min_pct: int
    max_pct: int

    def clamp(self, pct: int) -> int:
        return max(self.min_pct, min(self.max_pct, pct))


class CollectionListProgressTracker:
    """
    Tracks progress for an operation whose total work is not known up front.
    We maintain per-collection *estimates* (starting with a seed, then refining as we discover actuals)
    and map the cumulative fraction to a bounded [min_pct, max_pct] interval.
    """
    def __init__(self, progress_sink: Any, bounds: ProgressBounds, collection_count: int, initial_guess_per_collection: int = 40) -> None:
        self._progress_sink = progress_sink
        self._bounds = bounds
        self._estimates: List[int] = [initial_guess_per_collection] * collection_count  # mutable estimates
        self.actual: List[int] = []                      # discovered counts

    def record_collection_actual(self, index: int, actual_count: int) -> None:
        """
        Record actual item count for the collection list at 'index' and propagate that as the new best guess
        to all future collections that don't yet have an actual.
        """
        # Ensure list large enough and write actual at its slot
        if index < len(self._estimates):
            self._estimates[index] = actual_count
        # Append to actuals (we iterate items in order so index == len(actuals) is expected)
        self.actual.append(actual_count)

        # Update future unknown items to use this actual as the current best estimate
        for j in range(index + 1, len(self._estimates)):
            if j >= len(self.actual):
                self._estimates[j] = actual_count

    def mapped_pct(self) -> int:
        done = sum(self.actual)
        est_total = max(1, sum(self._estimates))
        # Linear mapping into the configured progress interval
        span = max(0, self._bounds.max_pct - self._bounds.min_pct)
        pct = self._bounds.min_pct + int((done / est_total) * span)
        return self._bounds.clamp(pct)

    def update(self, message: str) -> None:
        update_progress(self._progress_sink, self.mapped_pct(), message)


def weighted_progress_percent(
    progress_by_size: list[tuple[int, int | None]],
) -> int:
    """Return aggregate progress weighted by each item's expected byte size.

    Unknown sizes use the average known size so one legacy/missing item neither
    dominates the operation nor effectively disappears from the aggregate.
    """
    if not progress_by_size:
        return 100

    known_sizes = [
        int(size)
        for _progress, size in progress_by_size
        if size is not None and int(size) > 0
    ]
    fallback_size = (
        max(1, int(sum(known_sizes) / len(known_sizes)))
        if known_sizes
        else 1
    )

    weighted_progress = 0
    total_weight = 0
    for item_progress, size in progress_by_size:
        progress_value = max(0, min(100, int(item_progress)))
        weight = int(size) if size is not None and int(size) > 0 else fallback_size
        weighted_progress += progress_value * weight
        total_weight += weight

    return max(0, min(100, int(weighted_progress / max(1, total_weight))))


def update_progress(progress, percentage: int, msg: str):
    """Small helper to update the progress in any worker"""
    if progress:
        progress.set(percentage, msg)
    else:
        print(f"{percentage}%: {msg}")
