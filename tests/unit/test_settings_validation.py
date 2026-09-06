from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings.settings import AppSettings
from config.settings.submodels import (
    EpisodeStatusTiming,
    SchedulerSettings,
    SessionSettings,
    TimeoutSettings,
)


def test_runtime_settings_reject_invalid_timezone():
    with pytest.raises(ValidationError):
        AppSettings(timezone="Definitely/Not-A-Timezone")


def test_runtime_settings_reject_unsafe_session_timeout():
    with pytest.raises(ValidationError):
        SessionSettings(ttl_seconds=0)


def test_runtime_settings_reject_unsafe_request_pacing():
    with pytest.raises(ValidationError):
        TimeoutSettings(
            min_fast_request_ms=-1,
            max_fast_requests=0,
            min_slow_request_ms=-1,
        )


def test_runtime_settings_reject_unsafe_scheduler_limits():
    with pytest.raises(ValidationError):
        SchedulerSettings(
            enabled=True,
            max_workers=0,
            default_max_retries=-1,
            retry_backoff_seconds=-1,
        )


def test_runtime_settings_reject_final_episode_timing_before_countdown():
    with pytest.raises(ValidationError):
        EpisodeStatusTiming(
            published_countdown_after_minutes=20,
            published_final_after_minutes=10,
        )


def test_runtime_settings_default_no_usable_media_delete_delay_is_four_hours():
    timing = EpisodeStatusTiming(
        published_countdown_after_minutes=20,
        published_final_after_minutes=180,
    )

    assert timing.no_usable_media_delete_after_minutes == 240


def test_runtime_settings_reject_negative_no_usable_media_delete_delay():
    with pytest.raises(ValidationError):
        EpisodeStatusTiming(
            published_countdown_after_minutes=20,
            published_final_after_minutes=180,
            no_usable_media_delete_after_minutes=-1,
        )


def _settings_api_values() -> dict:
    from backend.api.models.settings import SettingsValues

    return SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )


def test_settings_api_rejects_invalid_runtime_cron_on_the_edited_field():
    from backend.api.models.settings import SettingsAPIUpdate

    values = _settings_api_values()
    values["newEpisodeSchedule"]["findEpisodesCron"] = "banana * * * *"

    with pytest.raises(ValidationError) as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["newEpisodeSchedule.findEpisodesCron"],
        })

    assert any(
        error["loc"] == ("values", "newEpisodeSchedule", "findEpisodesCron")
        for error in exc_info.value.errors()
    )


def test_settings_api_routes_cross_field_timing_error_to_final_field():
    from backend.api.models.settings import SettingsAPIUpdate

    values = _settings_api_values()
    values["episodeStatusTiming"]["publishedCountdownAfterMinutes"] = 20
    values["episodeStatusTiming"]["publishedFinalAfterMinutes"] = 10

    with pytest.raises(ValidationError) as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["episodeStatusTiming.publishedFinalAfterMinutes"],
        })

    assert any(
        error["loc"] == (
            "values",
            "episodeStatusTiming",
            "publishedFinalAfterMinutes",
        )
        for error in exc_info.value.errors()
    )


def test_settings_api_rejects_invalid_endpoint_url_on_the_edited_field():
    from backend.api.models.settings import SettingsAPIUpdate

    values = _settings_api_values()
    values["dwApi"]["middlewareApi"] = "not-a-url"

    with pytest.raises(ValidationError) as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["dwApi.middlewareApi"],
        })

    assert any(
        error["loc"] == ("values", "dwApi", "middlewareApi")
        for error in exc_info.value.errors()
    )
