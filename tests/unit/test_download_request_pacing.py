from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, time
from types import SimpleNamespace

import pytest

from dailywire_api import pacing


def policy(monkeypatch, *, slow=200, fast=0, maximum=0):
    monkeypatch.setattr(pacing, 'get_settings', lambda: SimpleNamespace(dw_timeout=SimpleNamespace(
        min_fast_request_ms=fast, min_slow_request_ms=slow, max_fast_requests=maximum,
    )))


def test_all_queue_followers_observe_global_cooldown(monkeypatch):
    policy(monkeypatch, slow=500)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    seen = [[], [], []]
    waiting = [Event(), Event(), Event()]
    def run(index):
        def observe(event):
            seen[index].append(event)
            if event and event.reason == 'daily_wire_request_cooldown':
                waiting[index].set()
        with pacing.request_context(observer=observe):
            pacer.wait()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, index) for index in range(3)]
        assert all(event.wait(2) for event in waiting)
        assert len(pacer.queue) == 3
        with pacer.condition:
            pacer.slow_cooldown_until = monotonic() - 1
            pacer.condition.notify_all()
        for future in futures:
            future.result(timeout=3)
    assert all(events[-1] is None for events in seen)
    assert all(any(event is not None and event.until is not None for event in events) for events in seen)


def test_canceling_queue_follower_does_not_leave_a_ticket_hole(monkeypatch):
    policy(monkeypatch, slow=300)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    cancel, enqueued = Event(), Event()
    def first():
        pacer.wait()
    def second():
        with pacing.request_context(should_cancel=cancel.is_set, observer=lambda event: enqueued.set() if event else None):
            pacer.wait()
    with ThreadPoolExecutor(max_workers=2) as pool:
        primary = pool.submit(first)
        follower = pool.submit(second)
        assert enqueued.wait(2)
        cancel.set()
        with pytest.raises(pacing.RequestCancelled):
            follower.result(timeout=2)
        primary.result(timeout=2)
    pacer.wait()
    assert not pacer.queue


def test_observer_runs_without_holding_pacing_lock(monkeypatch):
    policy(monkeypatch)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    def observe(event):
        if event is None:
            return
        acquired = Event()
        def acquire():
            with pacer.condition:
                acquired.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(acquire)
            assert acquired.wait(1)
            future.result()
    with pacing.request_context(observer=observe):
        pacer.wait()


def test_bulk_priority_precedes_background_until_aging():
    pacer = pacing.RequestPacer()
    now = monotonic()
    pacer.queue = {
        1: pacing._Ticket(1, 'background', now),
        2: pacing._Ticket(2, 'bulk', now),
    }
    assert pacer._next(now) == 2
    assert pacer._next(now + 31) == 1


def test_upstream_delay_is_observed_by_paced_priorities(monkeypatch):
    policy(monkeypatch, slow=0)
    pacer = pacing.RequestPacer()
    pacer.defer_upstream(.05)
    seen = []
    with pacing.request_context(observer=seen.append, priority='bulk'):
        pacer.wait()
    assert seen[0].reason == 'upstream_retry'
    assert seen[-1] is None


def test_interactive_execution_context_bypasses_wait_and_still_counts(monkeypatch):
    policy(monkeypatch, slow=1000, maximum=0)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    pacer.fast_requests = 1
    seen = []

    # Task workers inherit this ContextVar from the scheduler; their
    # MiddlewareClient usually does not pass an explicit request priority.
    with pacing.request_context(observer=seen.append, priority='interactive'):
        pacer.wait()

    assert pacer.queue == {}
    assert pacer.fast_requests == 2
    assert seen == []


def test_interactive_requests_bypass_wait_and_count_toward_background_cooldown(monkeypatch):
    policy(monkeypatch, slow=200, maximum=2)
    pacer = pacing.RequestPacer()

    # Interactive requests never enter the pacing queue, including while an
    # upstream restriction exists.
    pacer.defer_upstream(1)
    pacer.wait('interactive')
    pacer.wait('interactive')
    pacer.wait('interactive')
    assert pacer.queue == {}
    assert pacer.fast_requests == 3

    # Clear the unrelated upstream restriction so the next paced request exposes
    # the slow cooldown created by the interactive burst.
    with pacer.condition:
        pacer.upstream_until = 0
        pacer.upstream_until_wall = 0

    seen = []
    waiting = Event()

    def background():
        def observe(event):
            seen.append(event)
            if event and event.reason == 'daily_wire_request_cooldown':
                waiting.set()
        with pacing.request_context(observer=observe):
            pacer.wait('background')

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(background)
        assert waiting.wait(2)
        assert pacer.slow_cooldown_until is not None
        with pacer.condition:
            pacer.slow_cooldown_until = monotonic() - 1
            pacer.condition.notify_all()
        future.result(timeout=2)

    assert pacer.fast_requests == 1
    assert seen[-1] is None


def test_interactive_grace_does_not_extend_active_background_cooldown(monkeypatch):
    policy(monkeypatch, slow=500, maximum=0)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    pacer.fast_requests = 1

    waiting = Event()

    def background():
        def observe(event):
            if event and event.reason == 'daily_wire_request_cooldown':
                waiting.set()
        with pacing.request_context(observer=observe):
            pacer.wait('background')

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(background)
        assert waiting.wait(2)
        initial_deadline = pacer.slow_cooldown_until
        assert initial_deadline is not None

        for _ in range(pacing._SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS):
            pacer.wait('interactive')

        assert pacer.slow_cooldown_until == initial_deadline
        assert (
            pacer.slow_cooldown_unpaced_requests
            == pacing._SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS
        )

        with pacer.condition:
            pacer.slow_cooldown_until = monotonic() - 1
            pacer.condition.notify_all()
        future.result(timeout=2)


def test_interactive_request_beyond_grace_renews_background_cooldown(monkeypatch):
    policy(monkeypatch, slow=500, maximum=0)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    pacer.fast_requests = 1

    waiting = Event()

    def background():
        def observe(event):
            if event and event.reason == 'daily_wire_request_cooldown':
                waiting.set()
        with pacing.request_context(observer=observe):
            pacer.wait('background')

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(background)
        assert waiting.wait(2)
        initial_deadline = pacer.slow_cooldown_until
        assert initial_deadline is not None

        for _ in range(pacing._SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS):
            pacer.wait('interactive')

        pacer.wait('interactive')
        renewed_deadline = pacer.slow_cooldown_until
        assert renewed_deadline is not None
        assert renewed_deadline > initial_deadline
        assert (
            pacer.slow_cooldown_unpaced_requests
            == pacing._SLOW_COOLDOWN_UNPACED_GRACE_REQUESTS + 1
        )

        with pacer.condition:
            pacer.slow_cooldown_until = monotonic() - 1
            pacer.condition.notify_all()
        future.result(timeout=2)


def test_generic_non_download_executor_persists_follower_wait(task_database, monkeypatch):
    from sqlalchemy import select
    from task_manager.scheduler import registry
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task
    from task_manager.scheduler.db.TaskRun import TASK_RUN_WAIT_STATE_META_KEY
    policy(monkeypatch, slow=1000)
    pacer = pacing.RequestPacer()
    pacer.last_request, pacer.last_request_wall = monotonic(), time()
    monkeypatch.setattr(registry, '_REGISTRY', {})
    start = Event()
    @registry.task(key='cooldown_probe', title='Cooldown probe', allowed_resource_types=('show',), default_max_retries=0)
    def worker(*, resource_id=None, progress=None):
        start.set()
        pacer.wait()
    registry.sync_registry_to_db()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute_task, def_key='cooldown_probe', resource_type='show', resource_id=index) for index in [1, 2]]
        deadline = monotonic() + 3
        observed = False
        while monotonic() < deadline:
            with task_database() as session:
                runs = list(session.scalars(select(TaskRun)))
                observed = len(runs) == 2 and all((run.meta or {}).get(TASK_RUN_WAIT_STATE_META_KEY, {}).get('reason') == 'daily_wire_request_cooldown' for run in runs)
            if observed:
                break
            start.wait(.02)
        assert observed, 'Both unrelated TaskRuns must report the shared cooldown'
        with pacer.condition:
            pacer.slow_cooldown_until = monotonic() - 1
            pacer.condition.notify_all()
        for future in futures:
            future.result(timeout=4)
