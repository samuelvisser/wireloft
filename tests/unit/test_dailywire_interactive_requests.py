from types import SimpleNamespace


def test_catalog_ui_read_bypasses_background_pacing(monkeypatch):
    from backend.api.endpoints.dailywire.catalog import service

    captured: dict[str, object] = {}
    catalog = object()

    class FakeAuth:
        def get_token(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get_catalog(self):
            return catalog

    monkeypatch.setattr(service, "_catalog_cache", None)
    monkeypatch.setattr(service, "DeviceAuthClient", FakeAuth)
    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    assert service.get_catalog() is catalog
    assert captured["pace_requests"] is False


def test_show_preview_ui_read_bypasses_background_pacing(monkeypatch):
    from backend.api.endpoints.dailywire.shows import service

    captured: dict[str, object] = {}
    show = object()

    class FakeAuth:
        def get_token(self):
            return SimpleNamespace(access_token="token")

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get_show_page(self, *, slug, membership_plan):
            assert slug == "example-show"
            assert membership_plan == "ALL_ACCESS"
            return show

    monkeypatch.setattr(service, "DeviceAuthClient", FakeAuth)
    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    assert service.get_show("example-show", membership_plan="ALL_ACCESS") is show
    assert captured["access_token"] == "token"
    assert captured["pace_requests"] is False


def test_movie_ui_read_bypasses_background_pacing(monkeypatch):
    from backend.api.endpoints.dailywire.movies import service

    captured: dict[str, object] = {}
    movie = object()

    class FakeAuth:
        def get_token(self):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get_movie_page(self, slug):
            assert slug == "example-movie"
            return movie

    monkeypatch.setattr(service, "DeviceAuthClient", FakeAuth)
    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    assert service.get_movie("example-movie") is movie
    assert captured["pace_requests"] is False


def test_user_info_ui_read_bypasses_background_pacing(monkeypatch):
    from backend.api.endpoints.dailywire.user_info import service

    captured: dict[str, object] = {}
    user_info = object()

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get_user_info(self):
            return user_info

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    assert service.get_user_info() is user_info
    assert captured["pace_requests"] is False
