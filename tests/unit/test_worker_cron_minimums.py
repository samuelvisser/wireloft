from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings.settings import AppSettings


def _settings_document() -> dict:
    return AppSettings(timezone="UTC").model_dump(mode="python")


def _validate_with_cron(path: tuple[str, str], expression: str, *, slow_ms: int = 120_000):
    values = _settings_document()
    values["dw_timeout"]["min_slow_request_ms"] = slow_ms
    values[path[0]][path[1]] = expression
    return AppSettings.model_validate(values)


def test_default_monitor_interval_matches_slow_request_delay():
    settings = AppSettings(timezone="UTC")

    assert settings.new_episode_schedule.monitor_episode_cron == "*/2 * * * *"
    assert settings.dw_timeout.min_slow_request_ms == 120_000


@pytest.mark.parametrize(
    "path",
    [
        ("new_episode_schedule", "find_episodes_cron"),
        ("new_episode_schedule", "monitor_episode_cron"),
        ("new_episode_schedule", "check_no_show_today_cron"),
        ("download_settings", "verify_downloads_cron"),
        ("file_watcher", "scan_cron"),
    ],
)
def test_all_worker_crons_reject_intervals_shorter_than_slow_delay(path):
    with pytest.raises(ValidationError, match="requires at least 120 seconds"):
        _validate_with_cron(path, "* * * * *")


def test_worker_cron_accepts_interval_equal_to_slow_delay():
    settings = _validate_with_cron(
        ("new_episode_schedule", "monitor_episode_cron"),
        "*/2 * * * *",
    )

    assert settings.new_episode_schedule.monitor_episode_cron == "*/2 * * * *"


def test_worker_cron_uses_configured_slow_delay():
    with pytest.raises(ValidationError, match="requires at least 180 seconds"):
        _validate_with_cron(
            ("new_episode_schedule", "monitor_episode_cron"),
            "*/2 * * * *",
            slow_ms=180_000,
        )


def test_worker_cron_validation_handles_non_uniform_schedules():
    with pytest.raises(ValidationError, match="requires at least 120 seconds"):
        _validate_with_cron(
            ("new_episode_schedule", "monitor_episode_cron"),
            "0,1 0 * * *",
        )


def test_settings_api_rejects_too_fast_worker_cron_on_the_cron_field():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    values = SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )
    values["newEpisodeSchedule"]["monitorEpisodeCron"] = "* * * * *"

    with pytest.raises(ValidationError, match="requires at least 120 seconds") as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["newEpisodeSchedule.monitorEpisodeCron"],
        })

    matching_errors = [
        error
        for error in exc_info.value.errors()
        if error["loc"] == (
            "values",
            "newEpisodeSchedule",
            "monitorEpisodeCron",
        )
    ]
    assert len(matching_errors) == 1
    assert matching_errors[0]["type"] == "worker_cron_interval_too_short"


def test_settings_api_revalidates_crons_when_slow_delay_is_increased():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    values = SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )
    values["dwTimeout"]["minSlowRequestMs"] = 15 * 60 * 1000

    with pytest.raises(ValidationError, match="requires at least 900 seconds"):
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["dwTimeout.minSlowRequestMs"],
        })
