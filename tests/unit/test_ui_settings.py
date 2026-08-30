from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from config.registry import reload_settings
from config.settings.base import get_config_path
from config.settings.settings import AppSettings


def _point_settings_at(config_path, monkeypatch):
    monkeypatch.setenv("WL_CONFIG_FILE", str(config_path))
    monkeypatch.setitem(AppSettings.model_config, "yaml_file", config_path)
    return reload_settings()


def test_settings_use_one_config_yml(tmp_path, monkeypatch):
    config_path = tmp_path / "nested" / "config.yml"
    monkeypatch.setenv("WL_CONFIG_FILE", str(config_path))

    assert get_config_path() == config_path


def test_settings_api_contract_excludes_admin_and_literal_secrets():
    from backend.api.models.settings import CryptoFileSettingsValue, SettingsValues

    assert "admin_auth" not in SettingsValues.model_fields
    assert "database_path" not in SettingsValues.model_fields
    assert "app_version" not in SettingsValues.model_fields
    assert "secret_key" not in CryptoFileSettingsValue.model_fields


def test_settings_api_rejects_unexpected_admin_auth():
    from backend.api.models.settings import SettingsValues

    values = SettingsValues.from_app_settings(AppSettings()).model_dump(by_alias=True, mode="json")
    values["adminAuth"] = {"password": "must-not-be-accepted"}

    with pytest.raises(ValidationError, match="adminAuth"):
        SettingsValues.model_validate(values)


def test_settings_service_only_writes_changed_fields_and_preserves_other_yaml(tmp_path, monkeypatch):
    from backend.api.endpoints.settings.service import save_ui_settings
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "# This comment must survive UI edits.\n"
        "crypto:\n"
        "  defaultSecretFile: /config/existing.key\n"
        "downloadSettings:\n"
        "  downloadRoot: /downloads\n",
        encoding="utf-8",
    )
    settings = _point_settings_at(config_path, monkeypatch)

    values = SettingsValues.from_app_settings(settings)
    values.download_settings.max_concurrent_downloads = 9
    result = save_ui_settings(SettingsAPIUpdate(
        values=values,
        changed_fields=["downloadSettings.maxConcurrentDownloads"],
    ))

    text = config_path.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert "# This comment must survive UI edits." in text
    assert document["crypto"]["defaultSecretFile"] == "/config/existing.key"
    assert document["downloadSettings"]["downloadRoot"] == "/downloads"
    assert document["downloadSettings"]["maxConcurrentDownloads"] == 9
    assert "maxDownloadAttempts" not in document["downloadSettings"]
    assert "scheduler" not in document
    assert "adminAuth" not in document
    assert "databasePath" not in document
    assert "downloadSettings.maxConcurrentDownloads" in result.configured_fields
    assert result.values.download_settings.max_concurrent_downloads == 9
    assert not (tmp_path / "ui-settings.yml").exists()


def test_settings_service_updates_existing_scalar_without_removing_inline_comment(tmp_path, monkeypatch):
    from backend.api.endpoints.settings.service import save_ui_settings
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "logLevel: INFO  # keep this explanation\n"
        "downloadSettings:\n"
        "  downloadRoot: /downloads\n",
        encoding="utf-8",
    )
    settings = _point_settings_at(config_path, monkeypatch)

    values = SettingsValues.from_app_settings(settings)
    values.log_level = "DEBUG"
    save_ui_settings(SettingsAPIUpdate(values=values, changed_fields=["logLevel"]))

    text = config_path.read_text(encoding="utf-8")
    assert "logLevel: \"DEBUG\"  # keep this explanation" in text


def test_environment_overrides_are_reported_and_cannot_be_saved(tmp_path, monkeypatch):
    from backend.api.endpoints.settings.service import (
        SettingsManagedByEnvironmentError,
        get_ui_settings,
        save_ui_settings,
    )
    from backend.api.models.settings import SettingsAPIUpdate

    config_path = tmp_path / "config.yml"
    config_path.write_text("downloadSettings:\n  downloadRoot: /downloads\n", encoding="utf-8")
    monkeypatch.setenv("WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS", "8")
    _point_settings_at(config_path, monkeypatch)

    current = get_ui_settings()
    path = "downloadSettings.maxConcurrentDownloads"
    assert current.values.download_settings.max_concurrent_downloads == 8
    assert current.environment_overrides[path] == "WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS"

    values = current.values.model_copy(deep=True)
    values.download_settings.max_concurrent_downloads = 4
    with pytest.raises(SettingsManagedByEnvironmentError, match="WL_DOWNLOAD_SETTINGS__MAX_CONCURRENT_DOWNLOADS"):
        save_ui_settings(SettingsAPIUpdate(values=values, changed_fields=[path]))

    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "maxConcurrentDownloads" not in document["downloadSettings"]

    # Leave the process-wide registry source-derived for tests that follow.
    reload_settings()
