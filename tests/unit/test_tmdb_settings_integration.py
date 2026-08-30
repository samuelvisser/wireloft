from backend.api.models.settings import SettingsValues, UI_SETTING_PATHS
from config.settings.settings import AppSettings


def test_settings_api_never_returns_tmdb_token():
    settings = AppSettings(
        movie_metadata={
            "tmdb_read_access_token": "super-secret-token",
        }
    )

    values = SettingsValues.from_app_settings(settings)

    assert values.movie_metadata.tmdb_read_access_token == ""
    assert values.movie_metadata.tmdb_read_access_token_configured is True


def test_settings_api_reports_missing_tmdb_token_without_a_secret_value():
    settings = AppSettings(movie_metadata={"tmdb_read_access_token": None})

    values = SettingsValues.from_app_settings(settings)

    assert values.movie_metadata.tmdb_read_access_token == ""
    assert values.movie_metadata.tmdb_read_access_token_configured is False


def test_tmdb_settings_are_part_of_the_editable_settings_contract():
    assert "movieMetadata.tmdbReadAccessToken" in UI_SETTING_PATHS
    assert "movieMetadata.tmdbApiBaseUrl" in UI_SETTING_PATHS
    assert "movieMetadata.language" in UI_SETTING_PATHS
    assert "movieMetadata.requestTimeoutSeconds" in UI_SETTING_PATHS
    assert "movieMetadata.maxRetries" in UI_SETTING_PATHS
