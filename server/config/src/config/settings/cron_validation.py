from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger


_CRON_INTERVAL_SAMPLE_SIZE = 2048


class WorkerCronIntervalError(ValueError):
    """A worker cron can execute more often than the Daily Wire slow-request delay."""

    def __init__(
        self,
        *,
        setting_name: str,
        field_path: tuple[str, str],
        minimum_seconds: float,
        required_seconds: float,
    ) -> None:
        self.setting_name = setting_name
        self.field_path = field_path
        self.minimum_seconds = minimum_seconds
        self.required_seconds = required_seconds
        super().__init__(
            f"{setting_name} runs as often as every {minimum_seconds:g} seconds, "
            f"but Daily Wire slow-request delay requires at least {required_seconds:g} seconds"
        )


def minimum_cron_interval_seconds(expression: str) -> float:
    """Return the smallest observed gap between consecutive cron fire times.

    WireLoft accepts standard five-part cron expressions. APScheduler is the
    scheduler that executes them, so validation intentionally uses the same
    parser and fire-time semantics as runtime scheduling.
    """
    try:
        trigger = CronTrigger.from_crontab(expression, timezone=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid five-part cron expression") from exc

    previous = None
    now = datetime.now(timezone.utc)
    smallest: float | None = None

    for _ in range(_CRON_INTERVAL_SAMPLE_SIZE):
        current = trigger.get_next_fire_time(previous, now if previous is None else previous)
        if current is None:
            break
        if previous is not None:
            interval = (current - previous).total_seconds()
            if interval > 0 and (smallest is None or interval < smallest):
                smallest = interval
        previous = current

    if smallest is None:
        raise ValueError("Cron expression must produce recurring worker runs")
    return smallest


def validate_worker_cron_interval(
    expression: str,
    *,
    min_interval_ms: int,
    setting_name: str,
    field_path: tuple[str, str],
) -> None:
    minimum_seconds = minimum_cron_interval_seconds(expression)
    required_seconds = max(0, min_interval_ms) / 1000.0
    if minimum_seconds + 1e-9 < required_seconds:
        raise WorkerCronIntervalError(
            setting_name=setting_name,
            field_path=field_path,
            minimum_seconds=minimum_seconds,
            required_seconds=required_seconds,
        )


def validate_worker_cron_settings(
    *,
    min_slow_request_ms: int,
    find_episodes_cron_enabled: bool,
    find_episodes_cron: str,
    monitor_pending_episode_cron_enabled: bool,
    monitor_pending_episode_cron: str,
    monitor_no_usable_media_episode_cron_enabled: bool,
    monitor_no_usable_media_episode_cron: str,
    verify_downloads_cron_enabled: bool,
    verify_downloads_cron: str,
    file_watcher_scan_cron_enabled: bool,
    file_watcher_scan_cron: str,
) -> None:
    for enabled, setting_name, field_path, expression in (
        (
            find_episodes_cron_enabled,
            "Find episodes",
            ("new_episode_schedule", "find_episodes_cron"),
            find_episodes_cron,
        ),
        (
            monitor_pending_episode_cron_enabled,
            "Monitor pending episodes",
            ("new_episode_schedule", "monitor_pending_episode_cron"),
            monitor_pending_episode_cron,
        ),
        (
            monitor_no_usable_media_episode_cron_enabled,
            "Monitor no-usable-media episodes",
            ("new_episode_schedule", "monitor_no_usable_media_episode_cron"),
            monitor_no_usable_media_episode_cron,
        ),
        (
            verify_downloads_cron_enabled,
            "Verify downloads",
            ("download_settings", "verify_downloads_cron"),
            verify_downloads_cron,
        ),
        (
            file_watcher_scan_cron_enabled,
            "File watcher scan",
            ("file_watcher", "scan_cron"),
            file_watcher_scan_cron,
        ),
    ):
        if not enabled:
            continue
        validate_worker_cron_interval(
            expression,
            min_interval_ms=min_slow_request_ms,
            setting_name=setting_name,
            field_path=field_path,
        )
