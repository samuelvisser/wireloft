from threading import Thread
from time import monotonic, monotonic_ns, sleep
from types import SimpleNamespace

import pytest


def _reset_pacing_state(client) -> None:
    with client._pacing_condition:
        client._pacing_next_ticket = 0
        client._pacing_serving_ticket = 0
        client._last_request_ns = None
        client._ms_since_last_request = None
        client._fast_requests = 0
        client._pacing_condition.notify_all()


def _settings(*, min_fast_ms: int, max_fast: int, min_slow_ms: int):
    return SimpleNamespace(
        dw_timeout=SimpleNamespace(
            min_fast_request_ms=min_fast_ms,
            max_fast_requests=max_fast,
            min_slow_request_ms=min_slow_ms,
        )
    )


@pytest.fixture(autouse=True)
def reset_dailywire_pacing_state():
    from dailywire_api.dw_api import client

    _reset_pacing_state(client)
    yield
    _reset_pacing_state(client)


def test_slow_cooldown_starts_a_fresh_fast_request_burst(monkeypatch):
    from dailywire_api.dw_api import client

    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: _settings(min_fast_ms=1, max_fast=1, min_slow_ms=40),
    )

    # Pretend one fast request has already followed the previous request. The
    # next request therefore has to consume the slow cooldown.
    with client._pacing_condition:
        client._last_request_ns = monotonic_ns()
        client._fast_requests = 1

    client._wait_before_request()

    # The cooldown itself is the boundary between bursts. Requests already
    # queued behind it must not each inherit an over-limit counter and wait for
    # another full cooldown.
    assert client._fast_requests == 0

    previous_start_ns = client._last_request_ns
    client._wait_before_request()

    assert client._fast_requests == 1
    assert client._last_request_ns is not None
    assert previous_start_ns is not None
    assert client._last_request_ns - previous_start_ns < 40 * 1_000_000


def test_pacing_delay_releases_condition_lock_for_queued_callers(monkeypatch):
    from dailywire_api.dw_api import client

    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: _settings(min_fast_ms=0, max_fast=1, min_slow_ms=150),
    )

    with client._pacing_condition:
        client._last_request_ns = monotonic_ns()
        client._fast_requests = 1

    worker = Thread(target=client._wait_before_request, daemon=True)
    worker.start()

    # Wait until the worker has taken a ticket. At that point it should be in
    # its slow pacing wait, during which Condition.wait() must release the lock
    # so other Daily Wire callers can enqueue instead of blocking the state
    # mutex for the full cooldown.
    deadline = monotonic() + 0.1
    while client._pacing_next_ticket == 0 and monotonic() < deadline:
        sleep(0.001)

    assert client._pacing_next_ticket == 1
    acquired = client._pacing_condition.acquire(timeout=0.05)
    try:
        assert acquired
    finally:
        if acquired:
            client._pacing_condition.release()

    worker.join(timeout=0.5)
    assert not worker.is_alive()
