"""Process-wide, fair request starts and execution-scoped wait reporting.

Every queued caller observes a global cooldown, not only the caller selected to
start next. Callbacks execute outside the condition lock: persistence must never
hold up another caller's ability to enqueue or observe cancellation.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Condition
from time import monotonic, sleep, time
from typing import Callable, Iterator, Literal

from config import get_settings

logger = logging.getLogger(__name__)
RequestPriority = Literal["interactive", "bulk", "background"]


class RequestCancelled(InterruptedError):
    """A queued or retrying API request was canceled by its owning operation."""


@dataclass(frozen=True)
class RequestWait:
    reason: str
    until: float | None = None


_observer: ContextVar[Callable[[RequestWait | None], None] | None] = ContextVar("dailywire_request_observer", default=None)
_cancel: ContextVar[Callable[[], bool] | None] = ContextVar("dailywire_request_cancel", default=None)
_priority: ContextVar[RequestPriority] = ContextVar("dailywire_request_priority", default="background")


@contextmanager
def request_context(
    *, observer: Callable[[RequestWait | None], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    priority: RequestPriority | None = None,
) -> Iterator[None]:
    tokens = []
    for variable, value in ((_observer, observer), (_cancel, should_cancel), (_priority, priority)):
        if value is not None:
            tokens.append((variable, variable.set(value)))
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def check_cancelled() -> None:
    check = _cancel.get()
    if check is not None and check():
        raise RequestCancelled("Canceled while waiting for The Daily Wire")


def notify_wait(event: RequestWait | None) -> None:
    observer = _observer.get()
    if observer is not None:
        try:
            observer(event)
        except RequestCancelled:
            raise
        except Exception:
            # A progress sink can discover the same durable cancellation while
            # reporting the wait. Prefer the cancellation signal over logging
            # that expected control flow as an observer failure.
            check_cancelled()
            # Reporting is not permission to send a request. Cancellation is
            # checked independently, even when a reporting sink is unavailable.
            logger.exception("Could not report The Daily Wire request wait")


@dataclass(frozen=True)
class _Ticket:
    id: int
    priority: RequestPriority
    enqueued_at: float


class RequestPacer:
    def __init__(self):
        self.condition = Condition()
        self.queue: dict[int, _Ticket] = {}
        self.next_ticket = 0
        self.last_request: float | None = None
        self.last_request_wall: float | None = None
        self.fast_requests = 0
        self.foreground_streak = 0
        self.upstream_until = 0.0
        self.upstream_until_wall = 0.0

    def _next(self, now: float) -> int:
        tickets = tuple(self.queue.values())
        oldest = min(tickets, key=lambda item: item.id)
        # Aging and a bounded interactive burst prevent an ongoing stream of
        # clicks from indefinitely starving bulk work or scheduled discovery.
        if now - oldest.enqueued_at >= 30:
            return oldest.id
        ordinary = [item for item in tickets if item.priority != "interactive"]
        if self.foreground_streak >= 3 and ordinary:
            return min(ordinary, key=lambda item: item.id).id
        ranks = {"interactive": 0, "bulk": 1, "background": 2}
        return min(tickets, key=lambda item: (ranks[item.priority], item.id)).id

    def defer_upstream(self, seconds: float) -> None:
        with self.condition:
            candidate = monotonic() + max(0, seconds)
            if candidate > self.upstream_until:
                self.upstream_until = candidate
                self.upstream_until_wall = time() + max(0, seconds)
            self.condition.notify_all()

    def wait(self, priority: RequestPriority | None = None) -> None:
        policy = get_settings().dw_timeout
        fast_gap = max(0, policy.min_fast_request_ms / 1000)
        slow_gap = max(fast_gap, policy.min_slow_request_ms / 1000)
        maximum_fast = max(0, policy.max_fast_requests)
        selected_priority = priority or _priority.get()
        if selected_priority not in {"interactive", "bulk", "background"}:
            raise ValueError("Unknown request priority")
        with self.condition:
            ticket_id = self.next_ticket
            self.next_ticket += 1
            self.queue[ticket_id] = _Ticket(ticket_id, selected_priority, monotonic())
            self.condition.notify_all()
        previous: RequestWait | None = None
        completed = False
        try:
            while True:
                check_cancelled()
                with self.condition:
                    now = monotonic()
                    elapsed = now - self.last_request if self.last_request is not None else None
                    next_count = 0 if elapsed is None or elapsed >= slow_gap else self.fast_requests + 1
                    slow = next_count > maximum_fast
                    gap = slow_gap if slow else fast_gap
                    eligible = self.last_request + gap if self.last_request is not None else now
                    until_wall = self.last_request_wall + gap if self.last_request_wall is not None else None
                    reason = "daily_wire_request_cooldown" if slow else "request_spacing"
                    if self.upstream_until > max(now, eligible):
                        eligible = self.upstream_until
                        until_wall = self.upstream_until_wall
                        reason = "upstream_retry"
                    first = self._next(now) == ticket_id
                    if first and eligible <= now:
                        del self.queue[ticket_id]
                        self.last_request, self.last_request_wall = now, time()
                        self.fast_requests = 0 if slow else next_count
                        self.foreground_streak = self.foreground_streak + 1 if selected_priority == "interactive" else 0
                        self.condition.notify_all()
                        granted = True
                        event = None
                    else:
                        granted = False
                        # Followers share an active global restriction, even when
                        # they will also need to wait for their request turn.
                        event = RequestWait(reason, until_wall) if eligible > now else RequestWait("daily_wire_request_queue")
                    delay = min(0.1, max(0.001, eligible - now)) if eligible > now else 0.1
                if event != previous:
                    notify_wait(event)
                    previous = event
                if granted:
                    completed = True
                    return
                with self.condition:
                    self.condition.wait(timeout=delay)
        finally:
            with self.condition:
                self.queue.pop(ticket_id, None)
                self.condition.notify_all()
            # Do not clear a visible wait when cancellation interrupted it.
            # The owning operation transitions to Canceling instead. Clearing
            # here would emit a misleading "Preparing" checkpoint and, for a
            # canceled TaskRun, the observer itself can legitimately reject the
            # progress write as a cancellation signal.
            if completed and previous is not None:
                notify_wait(None)


pacer = RequestPacer()


def wait_before_request(priority: RequestPriority | None = None) -> None:
    pacer.wait(priority)


def wait_for_retry(error: Exception, attempt: int, *, base_delay: float = 1.5) -> None:
    delay = base_delay * (attempt + 1)
    reason = "retry_backoff"
    raw = getattr(error, "headers", {}).get("Retry-After") if getattr(error, "headers", None) else None
    if raw:
        try:
            delay = max(0, float(raw))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                delay = max(0, (parsed - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                raw = None
        if raw:
            reason = "upstream_retry"
            pacer.defer_upstream(delay)
    deadline = monotonic() + delay
    notify_wait(RequestWait(reason, time() + delay))
    completed = False
    try:
        while True:
            check_cancelled()
            remaining = deadline - monotonic()
            if remaining <= 0:
                completed = True
                return
            sleep(min(remaining, 0.1))
    finally:
        if completed:
            notify_wait(None)
