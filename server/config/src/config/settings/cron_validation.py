from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger


_CRON_INTERVAL_SAMPLE_SIZE = 2048


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
) -> None:
    minimum_seconds = minimum_cron_interval_seconds(expression)
    required_seconds = max(0, min_interval_ms) / 1000.0
    if minimum_seconds + 1e-9 < required_seconds:
        raise ValueError(
            f"{setting_name} runs as often as every {minimum_seconds:g} seconds, "
            f"but Daily Wire slow-request delay requires at least {required_seconds:g} seconds"
        )


def validate_worker_cron_settings(
    *,
    min_slow_request_ms: int,
    find_episodes_cron: str,
    monitor_episode_cron: str,
    check_no_show_today_cron: str,
    verify_downloads_cron: str,
    file_watcher_scan_cron: str,
) -> None:
    for setting_name, expression in (
        ("Find episodes", find_episodes_cron),
        ("Monitor pending episodes", monitor_episode_cron),
        ("Check no-show-today episodes", check_no_show_today_cron),
        ("Verify downloads", verify_downloads_cron),
        ("File watcher scan", file_watcher_scan_cron),
    ):
        validate_worker_cron_interval(
            expression,
            min_interval_ms=min_slow_request_ms,
            setting_name=setting_name,
        )
