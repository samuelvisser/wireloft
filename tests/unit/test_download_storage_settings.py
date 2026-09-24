from __future__ import annotations


def test_system_download_storage_defaults_to_direct_mode():
    from backend.api.models.settings import SettingsValues
    from config.settings.settings import AppSettings
    from config.settings.submodels import DownloadMode, ThumbnailMode

    settings = AppSettings()

    assert settings.download_settings.download_mode is DownloadMode.DIRECT
    assert settings.download_settings.thumbnail_mode is ThumbnailMode.EMBED
    assert (
        settings.download_settings.temporary_download_root
        == settings.download_settings.download_root / ".wireloft-temp"
    )
    assert (
        settings.download_settings.rss_cache_root
        == settings.download_settings.download_root / ".wireloft-rss-cache"
    )
    assert settings.download_settings.rss_cache_retention_seconds == 7 * 24 * 60 * 60

    values = SettingsValues.from_app_settings(settings).model_dump(
        by_alias=True,
        mode="json",
    )
    assert values["downloadSettings"]["downloadMode"] == "direct"
    assert values["downloadSettings"]["thumbnailMode"] == "embed"
    assert values["downloadSettings"]["temporaryDownloadRoot"] == str(
        settings.download_settings.download_root / ".wireloft-temp"
    )
    assert values["downloadSettings"]["rssCacheRoot"] == str(
        settings.download_settings.download_root / ".wireloft-rss-cache"
    )
    assert values["downloadSettings"]["rssCacheRetentionSeconds"] == 7 * 24 * 60 * 60


def test_download_storage_default_factories_follow_download_root():
    from config.settings.submodels import DownloadSettings

    settings = DownloadSettings(download_root="/media")

    assert settings.temporary_download_root.as_posix() == "/media/.wireloft-temp"
    assert settings.rss_cache_root.as_posix() == "/media/.wireloft-rss-cache"


def test_explicit_download_storage_paths_override_default_factories():
    from config.settings.submodels import DownloadSettings

    settings = DownloadSettings(
        download_root="/media",
        temporary_download_root="/tmp/wireloft-downloads",
        rss_cache_root="/tmp/wireloft-rss-cache",
    )

    assert settings.temporary_download_root.as_posix() == "/tmp/wireloft-downloads"
    assert settings.rss_cache_root.as_posix() == "/tmp/wireloft-rss-cache"


def test_local_media_profile_defaults_to_system_storage_and_thumbnail_modes():
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    body = ShowLocalMediaProfileAPICreate(
        name="Audio",
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
    )

    assert str(body.download_mode) == "system"
    assert str(body.thumbnail_mode) == "system"
    payload = body.model_dump(by_alias=True, mode="json")
    assert payload["download_mode"] == "system"
    assert payload["thumbnail_mode"] == "system"


def test_local_media_profile_accepts_each_storage_override():
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    for mode in ("system", "direct", "temporary"):
        body = ShowLocalMediaProfileAPICreate(
            name=f"Audio {mode}",
            type="show",
            preferred_format="format_audio_only",
            download_mode=mode,
            output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
        )
        assert str(body.download_mode) == mode


def test_local_media_profile_accepts_each_thumbnail_override():
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    for mode in ("system", "no_thumbnail", "embed", "sidecar", "embed_and_sidecar"):
        body = ShowLocalMediaProfileAPICreate(
            name=f"Audio {mode}",
            type="show",
            preferred_format="format_audio_only",
            thumbnail_mode=mode,
            output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
        )
        assert str(body.thumbnail_mode) == mode


def test_download_profile_no_longer_contains_storage_mode():
    from backend.api.models.download_profile import DownloadProfileAPICreate

    body = DownloadProfileAPICreate(
        show_id=1,
        local_media_profile_id=2,
        enable_profile=True,
        ep_id_type_list=[],
    )

    assert "download_mode" not in body.model_dump(by_alias=True, mode="json")
