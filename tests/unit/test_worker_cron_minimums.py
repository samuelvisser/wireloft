from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings.cron_validation import (
    CronExpressionError,
    minimum_cron_interval_seconds,
    validate_cron_expression,
    worker_cron_validation_errors,
)
from config.settings.settings import AppSettings


def _settings_document() -> dict:
    return AppSettings(timezone="UTC").model_dump(mode="python")


def _worker_kwargs(settings: AppSettings) -> dict:
    return {
        "min_slow_request_ms": settings.dw_timeout.min_slow_request_ms,
        "find_episodes_cron_enabled": settings.new_episode_schedule.find_episodes_cron_enabled,
        "find_episodes_cron": settings.new_episode_schedule.find_episodes_cron,
        "monitor_pending_episode_cron_enabled": settings.new_episode_schedule.monitor_pending_episode_cron_enabled,
        "monitor_pending_episode_cron": settings.new_episode_schedule.monitor_pending_episode_cron,
        "monitor_no_usable_media_episode_cron_enabled": settings.new_episode_schedule.monitor_no_usable_media_episode_cron_enabled,
        "monitor_no_usable_media_episode_cron": settings.new_episode_schedule.monitor_no_usable_media_episode_cron,
        "verify_downloads_cron_enabled": settings.download_settings.verify_downloads_cron_enabled,
        "verify_downloads_cron": settings.download_settings.verify_downloads_cron,
        "file_watcher_scan_cron_enabled": settings.file_watcher.scan_cron_enabled,
        "file_watcher_scan_cron": settings.file_watcher.scan_cron,
    }


@pytest.mark.parametrize(
    ("expression", "minimum_seconds"),
    [
        ("* * * * *", 60),
        ("0,1 0 * * *", 60),
        ("5/10 * * * *", 10 * 60),
        ("*/2 * * * *", 120),
        ("0 */2 * * *", 2 * 60 * 60),
        ("0 0 * * mon", 7 * 24 * 60 * 60),
        ("0 0 last * *", 28 * 24 * 60 * 60),
        ("0 0 29 feb *", 1461 * 24 * 60 * 60),
    ],
)
def test_static_cron_analyzer_finds_exact_minimum(expression, minimum_seconds):
    assert minimum_cron_interval_seconds(expression) == minimum_seconds


@pytest.mark.parametrize(
    "expression",
    [
        "banana * * * *",
        "* * * *",
        "60 * * * *",
        "*/0 * * * *",
        "0 0 */31 * *",
        "0 0 1 jan/2 *",
        "0 0 * * mon/2",
        "0 0 1 jan-3 *",
        "0 0 32 * *",
    ],
)
def test_static_cron_analyzer_rejects_invalid_expressions(expression):
    with pytest.raises(CronExpressionError):
        validate_cron_expression(expression)


def test_runtime_settings_no_longer_repeat_worker_policy_validation():
    values = _settings_document()
    values["new_episode_schedule"]["monitor_pending_episode_cron"] = "* * * * *"

    settings = AppSettings.model_validate(values)

    assert settings.new_episode_schedule.monitor_pending_episode_cron == "* * * * *"


def test_startup_worker_validation_reports_too_fast_cron():
    settings = AppSettings(timezone="UTC")
    values = settings.model_dump(mode="python")
    values["new_episode_schedule"]["monitor_pending_episode_cron"] = "* * * * *"
    settings = AppSettings.model_validate(values)

    errors = worker_cron_validation_errors(**_worker_kwargs(settings))

    matching = [
        error
        for error in errors
        if error.field_path == ("new_episode_schedule", "monitor_pending_episode_cron")
    ]
    assert len(matching) == 1
    assert "requires at least 120 seconds" in str(matching[0])


def test_disabled_worker_cron_skips_minimum_interval_validation():
    settings = AppSettings(timezone="UTC")
    values = settings.model_dump(mode="python")
    values["new_episode_schedule"]["find_episodes_cron_enabled"] = False
    values["new_episode_schedule"]["find_episodes_cron"] = "* * * * *"
    settings = AppSettings.model_validate(values)

    errors = worker_cron_validation_errors(**_worker_kwargs(settings))

    assert not any(
        error.field_path == ("new_episode_schedule", "find_episodes_cron")
        for error in errors
    )


def test_disabled_invalid_cron_is_not_a_startup_issue():
    settings = AppSettings(timezone="UTC")
    values = settings.model_dump(mode="python")
    values["new_episode_schedule"]["find_episodes_cron_enabled"] = False
    values["new_episode_schedule"]["find_episodes_cron"] = "banana * * * *"
    settings = AppSettings.model_validate(values)

    errors = worker_cron_validation_errors(**_worker_kwargs(settings))

    assert not any(
        error.field_path == ("new_episode_schedule", "find_episodes_cron")
        for error in errors
    )


def test_settings_api_rejects_too_fast_worker_cron_on_the_cron_field():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    values = SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )
    values["newEpisodeSchedule"]["monitorPendingEpisodeCron"] = "* * * * *"

    with pytest.raises(ValidationError, match="requires at least 120 seconds") as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["newEpisodeSchedule.monitorPendingEpisodeCron"],
        })

    matching_errors = [
        error
        for error in exc_info.value.errors()
        if error["loc"] == (
            "values",
            "newEpisodeSchedule",
            "monitorPendingEpisodeCron",
        )
    ]
    assert len(matching_errors) == 1
    assert matching_errors[0]["type"] == "worker_cron_interval_too_short"


def test_settings_api_rejects_invalid_worker_cron_on_the_cron_field():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    values = SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )
    values["newEpisodeSchedule"]["findEpisodesCron"] = "banana * * * *"

    with pytest.raises(ValidationError) as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["newEpisodeSchedule.findEpisodesCron"],
        })

    matching_errors = [
        error
        for error in exc_info.value.errors()
        if error["loc"] == (
            "values",
            "newEpisodeSchedule",
            "findEpisodesCron",
        )
    ]
    assert len(matching_errors) == 1
    assert matching_errors[0]["type"] == "cron_expression_invalid"


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


def test_existing_startup_cron_issue_does_not_block_unrelated_save():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    settings = AppSettings(timezone="UTC")
    values = settings.model_dump(mode="python")
    values["new_episode_schedule"]["monitor_pending_episode_cron"] = "* * * * *"
    settings = AppSettings.model_validate(values)

    api_values = SettingsValues.from_app_settings(settings).model_dump(
        by_alias=True,
        mode="json",
    )
    api_values["scheduler"]["maxWorkers"] += 1

    update = SettingsAPIUpdate.model_validate({
        "values": api_values,
        "changedFields": ["scheduler.maxWorkers"],
    })

    assert update.values.scheduler.max_workers == settings.scheduler.max_workers + 1


def test_settings_api_still_validates_cron_syntax_while_disabled():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    values = SettingsValues.from_app_settings(AppSettings(timezone="UTC")).model_dump(
        by_alias=True,
        mode="json",
    )
    values["newEpisodeSchedule"]["findEpisodesCronEnabled"] = False
    values["newEpisodeSchedule"]["findEpisodesCron"] = "banana * * * *"

    with pytest.raises(ValidationError) as exc_info:
        SettingsAPIUpdate.model_validate({
            "values": values,
            "changedFields": ["newEpisodeSchedule.findEpisodesCron"],
        })

    assert any(
        error["type"] == "cron_expression_invalid"
        for error in exc_info.value.errors()
    )


def test_settings_api_allows_disabling_preexisting_invalid_cron():
    from backend.api.models.settings import SettingsAPIUpdate, SettingsValues

    settings = AppSettings(timezone="UTC")
    current = settings.model_dump(mode="python")
    current["new_episode_schedule"]["find_episodes_cron"] = "banana * * * *"
    settings = AppSettings.model_validate(current)
    values = SettingsValues.from_app_settings(settings).model_dump(
        by_alias=True,
        mode="json",
    )
    values["newEpisodeSchedule"]["findEpisodesCronEnabled"] = False

    update = SettingsAPIUpdate.model_validate({
        "values": values,
        "changedFields": ["newEpisodeSchedule.findEpisodesCronEnabled"],
    })

    assert update.values.new_episode_schedule.find_episodes_cron_enabled is False
