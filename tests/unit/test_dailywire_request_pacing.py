from __future__ import annotations


def _fake_response():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{}"

    return FakeResponse()


def test_middleware_client_uses_global_pacing_by_default(monkeypatch):
    from dailywire_api.dw_api import client

    priorities = []
    monkeypatch.setattr(
        client,
        "wait_before_request",
        lambda priority=None: priorities.append(priority),
    )
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: _fake_response())

    middleware = client.MiddlewareClient(base_url="https://example.invalid")
    assert middleware._get("v4/test") == {}
    assert priorities == [None]


def test_interactive_middleware_client_preserves_pacing_override(monkeypatch):
    from dailywire_api.dw_api import client

    priorities = []
    monkeypatch.setattr(
        client,
        "wait_before_request",
        lambda priority=None: priorities.append(priority),
    )
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: _fake_response())

    middleware = client.MiddlewareClient(
        base_url="https://example.invalid",
        request_priority="interactive",
    )
    assert middleware._get("v4/test") == {}
    assert priorities == ["interactive"]


def test_explicit_pace_requests_false_preserves_bypass(monkeypatch):
    from dailywire_api.dw_api import client

    priorities = []
    monkeypatch.setattr(
        client,
        "wait_before_request",
        lambda priority=None: priorities.append(priority),
    )
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: _fake_response())

    middleware = client.MiddlewareClient(
        base_url="https://example.invalid",
        pace_requests=False,
    )
    assert middleware._get("v4/test") == {}
    assert priorities == ["interactive"]
