from types import SimpleNamespace

from backend.api.endpoints.puller import service
from backend.services import push_notifications


def test_frontend_pull_includes_application_version(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(app_version="9.8.7"),
    )
    monkeypatch.setattr(service, "list_operations", lambda **_kwargs: [])

    monkeypatch.setattr(push_notifications, "_foreground_last_seen", 0.0)
    response = service.get_frontend_pull()

    assert response.app_version == "9.8.7"
    assert push_notifications.foreground_recent()
    assert response.model_dump(by_alias=True)["appVersion"] == "9.8.7"
