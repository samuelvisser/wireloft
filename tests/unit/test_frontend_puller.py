from types import SimpleNamespace

from backend.api.endpoints.puller import service


def test_frontend_pull_includes_application_version(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(app_version="9.8.7"),
    )
    monkeypatch.setattr(service, "list_operations", lambda **_kwargs: [])

    response = service.get_frontend_pull()

    assert response.app_version == "9.8.7"
    assert response.model_dump(by_alias=True)["appVersion"] == "9.8.7"
