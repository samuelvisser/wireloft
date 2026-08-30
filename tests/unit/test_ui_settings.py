from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from config.registry import reload_settings
from config.settings.base import get_ui_config_path
from config.settings.settings import AppSettings


def test_ui_settings_file_overrides_config_yml_but_not_environment(tmp_path, monkeypatch):
    base_config = tmp_path / "config.yml"
    ui_config = tmp_path / "ui-settings.yml"
    base_config.write_text(
        "logLevel: WARNING\n"
        "downloadSettings:\n"
        "  maxConcurrentDownloads: 2\n",
        encoding="utf-8",
    )
    ui_config.write_text(
        "logLevel: DEBUG\n"
        "downloadSettings:\n"
        "  maxConcurrentDownloads: 7\n",
        encoding="utf-8",
    )

    monkeypatch.setitem(AppSettings.model_config, "yaml_file", base_config)
    monkeypatch.setenv("WL_UI_CONFIG_FILE", str(ui_config))
    monkeypatch.setenv("WL_LOG_LEVEL", "ERROR")

    settings = AppSettings()

    assert settings.log_level == "ERROR"
    assert settings.download_settings.max_concurrent_downloads == 7


def test_ui_settings_path_defaults_beside_config_yml(tmp_path, monkeypatch):
    config_path = tmp_path / "nested" / "config.yml"
    monkeypatch.delenv("WL_UI_CONFIG_FILE", raising=False)
    monkeypatch.setenv("WL_CONFIG_FILE", str(config_path))

    assert get_ui_config_path() == config_path.with_name("ui-settings.yml")


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

    try:
        SettingsValues.model_validate(values)
    except ValidationError as exc:
        assert "adminAuth" in str(exc)
    else:
        raise AssertionError("SettingsValues unexpectedly accepted admin authentication data")


def test_settings_service_writes_only_whitelisted_values(tmp_path, monkeypatch):
    from backend.api.endpoints.settings.service import reset_ui_settings, save_ui_settings
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    ui_config = tmp_path / "ui-settings.yml"
    monkeypatch.setenv("WL_UI_CONFIG_FILE", str(ui_config))

    values = SettingsValues.from_app_settings(AppSettings())
    values.download_settings.max_concurrent_downloads = 9
    result = save_ui_settings(SettingsAPIUpdate(values=values))

    document = yaml.safe_load(ui_config.read_text(encoding="utf-8"))
    assert document["downloadSettings"]["maxConcurrentDownloads"] == 9
    assert "adminAuth" not in document
    assert "databasePath" not in document
    assert "secretKey" not in document["crypto"]
    assert result.has_overrides is True
    assert result.values.download_settings.max_concurrent_downloads == 9

    reset_result = reset_ui_settings()
    assert not ui_config.exists()
    assert reset_result.has_overrides is False

    # Leave the process-wide registry in its ordinary, source-derived state for
    # tests that run after this module.
    reload_settings()
