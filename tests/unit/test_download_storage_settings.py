from __future__ import annotations


def test_system_download_storage_defaults_to_direct_mode():
    from backend.api.models.settings import SettingsValues
    from config.settings.settings import AppSettings
    from config.settings.submodels import DownloadMode

    settings = AppSettings()

    assert settings.download_settings.download_mode is DownloadMode.DIRECT
    assert settings.download_settings.temporary_download_root.name == ".wireloft-temp"

    values = SettingsValues.from_app_settings(settings).model_dump(
        by_alias=True,
        mode="json",
    )
    assert values["downloadSettings"]["downloadMode"] == "direct"
    assert values["downloadSettings"]["temporaryDownloadRoot"]


def test_download_profile_defaults_to_system_storage_mode():
    from backend.api.models.download_profile import DownloadProfileAPICreate

    body = DownloadProfileAPICreate(
        show_id=1,
        local_media_profile_id=2,
        enable_profile=True,
        ep_id_type_list=[],
    )

    assert str(body.download_mode) == "system"
    assert body.model_dump(by_alias=True, mode="json")["download_mode"] == "system"


def test_download_profile_accepts_each_storage_override():
    from backend.api.models.download_profile import DownloadProfileAPICreate

    for mode in ("system", "direct", "temporary"):
        body = DownloadProfileAPICreate(
            show_id=1,
            local_media_profile_id=2,
            enable_profile=True,
            download_mode=mode,
            ep_id_type_list=[],
        )
        assert str(body.download_mode) == mode
