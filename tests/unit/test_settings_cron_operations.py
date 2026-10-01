from __future__ import annotations


def test_settings_cron_operations_target_the_scheduled_workers():
    from backend.api.endpoints.settings.operations import (
        FileWatcherCronOperation,
        FindEpisodesCronOperation,
        MonitorNoUsableMediaCronOperation,
        VerifyDownloadsCronOperation,
    )

    cases = (
        (FindEpisodesCronOperation(), "fetch_new_episodes", "show"),
        (MonitorNoUsableMediaCronOperation(), "monitor_no_usable_media_episode", "show"),
        (VerifyDownloadsCronOperation(), "download_profile_worker", "download_profile"),
        (FileWatcherCronOperation(), "file_watcher", "show"),
    )

    for operation, task_key, resource_type in cases:
        targets = operation.targets()
        assert len(targets) == 1
        target = targets[0]
        assert target.task_key == task_key
        assert target.resource_type == resource_type
        assert target.resource_id == 0


def test_pending_episode_cron_operation_targets_each_pending_episode():
    from backend.api.endpoints.settings.operations import MonitorPendingEpisodesCronOperation

    operation = MonitorPendingEpisodesCronOperation((9, 4, 9))

    assert operation.resource_type == "system"
    assert operation.resource_id == 0
    assert operation.context() == {"episodes_requested": 2}
    assert [
        (target.task_key, target.resource_type, target.resource_id, target.slot_key)
        for target in operation.targets()
    ] == [
        ("monitor_pending_episode", "episode", 9, "episode:9"),
        ("monitor_pending_episode", "episode", 4, "episode:4"),
    ]


def test_settings_cron_operations_have_distinct_system_kinds():
    from backend.api.endpoints.settings.operations import (
        FileWatcherCronOperation,
        FindEpisodesCronOperation,
        MonitorNoUsableMediaCronOperation,
        MonitorPendingEpisodesCronOperation,
        VerifyDownloadsCronOperation,
    )

    operations = (
        FindEpisodesCronOperation(),
        MonitorPendingEpisodesCronOperation(()),
        MonitorNoUsableMediaCronOperation(),
        VerifyDownloadsCronOperation(),
        FileWatcherCronOperation(),
    )

    assert {operation.kind for operation in operations} == {
        "system.cron.find_episodes",
        "system.cron.monitor_pending_episodes",
        "system.cron.monitor_no_usable_media",
        "system.cron.verify_downloads",
        "system.cron.file_watcher",
    }
