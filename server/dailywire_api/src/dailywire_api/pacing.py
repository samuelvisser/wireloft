"""Process-wide request pacing and execution-scoped wait reporting.

Bulk/background callers share fair pacing and cooldowns. Interactive callers
start immediately but still contribute to the global burst accounting used to
defer subsequent paced work. Callbacks execute outside the condition lock so
persistence never blocks request queuing.
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
_SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS = 10


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
        self.slow_cooldown_until: float | None = None
        self.slow_cooldown_until_wall: float | None = None
        self.slow_cooldown_unpaced_requests = 0

    def _next(self, now: float) -> int:
        tickets = tuple(self.queue.values())
        oldest = min(tickets, key=lambda item: item.id)
        # Interactive requests bypass this queue entirely. Bulk work gets
        # preference over background work, while aging prevents starvation.
        if now - oldest.enqueued_at >= 30:
            return oldest.id
        ranks = {"bulk": 0, "background": 1, "interactive": 2}
        return min(tickets, key=lambda item: (ranks[item.priority], item.id)).id

    def _request_state(self, now: float, slow_gap: float) -> tuple[float | None, int]:
        """Return elapsed time and the burst count including this request."""
        if self.last_request is None:
            return None, 1

        elapsed = max(0.0, now - self.last_request)
        if elapsed >= slow_gap:
            return elapsed, 1
        return elapsed, self.fast_requests + 1

    def record_unpaced(self) -> None:
        """Record an interactive request without making it wait.

        Interactive requests use WireLoft's explicit pacing override, but
        every actual Daily Wire request still contributes to the shared burst
        history seen by paced bulk/background work.

        While a slow cooldown is already active, a small number of interactive
        requests are tolerated without moving its deadline. This prevents light
        RSS/UI traffic from indefinitely starving background work. Once the
        grace threshold is crossed, each further request renews the cooldown.
        """
        policy = get_settings().dw_timeout
        fast_gap = max(0.0, policy.min_fast_request_ms / 1000)
        slow_gap = max(fast_gap, policy.min_slow_request_ms / 1000)

        with self.condition:
            now = monotonic()
            now_wall = time()

            if (
                self.slow_cooldown_until is not None
                and now >= self.slow_cooldown_until
            ):
                self.slow_cooldown_until = None
                self.slow_cooldown_until_wall = None
                self.slow_cooldown_unpaced_requests = 0

            active_cooldown = self.slow_cooldown_until is not None
            _, next_count = self._request_state(now, slow_gap)
            self.last_request = now
            self.last_request_wall = now_wall
            self.fast_requests = next_count
            self.foreground_streak += 1

            if active_cooldown:
                self.slow_cooldown_unpaced_requests += 1
                if (
                    self.slow_cooldown_unpaced_requests
                    > _SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS
                ):
                    self.slow_cooldown_until = now + slow_gap
                    self.slow_cooldown_until_wall = now_wall + slow_gap
                    self.condition.notify_all()
                return

            # A paced request may be sleeping for ordinary spacing. Wake it so
            # it can account for this newer request and burst count.
            self.condition.notify_all()

    def defer_upstream(self, seconds: float) -> None:
        with self.condition:
            candidate = monotonic() + max(0, seconds)
            if candidate > self.upstream_until:
                self.upstream_until = candidate
                self.upstream_until_wall = time() + max(0, seconds)
            self.condition.notify_all()

    def wait(self, priority: RequestPriority | None = None) -> None:
        selected_priority = priority or _priority.get()
        if selected_priority not in {"interactive", "bulk", "background"}:
            raise ValueError("Unknown request priority")

        # user-interactive API calls never wait for global pacing.
        if selected_priority == "interactive":
            check_cancelled()
            self.record_unpaced()
            return

        policy = get_settings().dw_timeout
        fast_gap = max(0.0, policy.min_fast_request_ms / 1000)
        slow_gap = max(fast_gap, policy.min_slow_request_ms / 1000)
        maximum_fast = max(0, policy.max_fast_requests)

        with self.condition:
            ticket_id = self.next_ticket
            self.next_ticket += 1
            self.queue[ticket_id] = _Ticket(
                ticket_id,
                selected_priority,
                monotonic(),
            )
            self.condition.notify_all()

        previous: RequestWait | None = None
        try:
            while True:
                check_cancelled()
                with self.condition:
                    now = monotonic()

                    # The slow cooldown is a burst boundary. Interactive requests
                    # inside its grace window may be newer than the original
                    # trigger, but intentionally do not move this boundary.
                    if (
                        self.slow_cooldown_until is not None
                        and now >= self.slow_cooldown_until
                    ):
                        self.slow_cooldown_until = None
                        self.slow_cooldown_until_wall = None
                        self.slow_cooldown_unpaced_requests = 0
                        self.last_request = None
                        self.last_request_wall = None
                        self.fast_requests = 0

                    next_count: int | None = None
                    if self.slow_cooldown_until is not None:
                        eligible = self.slow_cooldown_until
                        until_wall = self.slow_cooldown_until_wall
                        reason = "daily_wire_request_cooldown"
                    else:
                        _, next_count = self._request_state(now, slow_gap)
                        if self.last_request is None:
                            slow = False
                            eligible = now
                            until_wall = None
                        else:
                            slow = next_count > maximum_fast
                            gap = slow_gap if slow else fast_gap
                            eligible = self.last_request + gap
                            until_wall = (
                                self.last_request_wall + gap
                                if self.last_request_wall is not None
                                else None
                            )

                        reason = (
                            "daily_wire_request_cooldown"
                            if slow
                            else "request_spacing"
                        )
                        if slow and eligible > now:
                            self.slow_cooldown_until = eligible
                            self.slow_cooldown_until_wall = until_wall
                            self.slow_cooldown_unpaced_requests = 0

                    if self.upstream_until > max(now, eligible):
                        eligible = self.upstream_until
                        until_wall = self.upstream_until_wall
                        reason = "upstream_retry"

                    first = self._next(now) == ticket_id
                    if first and eligible <= now:
                        del self.queue[ticket_id]
                        self.last_request = now
                        self.last_request_wall = time()
                        self.fast_requests = next_count if next_count is not None else 1
                        self.foreground_streak = 0
                        self.condition.notify_all()
                        granted = True
                        event = None
                    else:
                        granted = False
                        # Followers share an active global restriction, even when
                        # they will also need to wait for their request turn.
                        event = (
                            RequestWait(reason, until_wall)
                            if eligible > now
                            else RequestWait("daily_wire_request_queue")
                        )
                    delay = (
                        min(0.1, max(0.001, eligible - now))
                        if eligible > now
                        else 0.1
                    )

                if event != previous:
                    notify_wait(event)
                    previous = event
                if granted:
                    return

                with self.condition:
                    self.condition.wait(timeout=delay)
        finally:
            with self.condition:
                self.queue.pop(ticket_id, None)
                self.condition.notify_all()
            if previous is not None:
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
    try:
        while True:
            check_cancelled()
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            sleep(min(remaining, 0.1))
    finally:
        notify_wait(None)
