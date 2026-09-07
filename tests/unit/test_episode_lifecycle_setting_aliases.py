def test_legacy_episode_monitor_environment_names_are_not_translated():
    from config.settings.settings import AppSettings, environment_settings_source_data

    class FakeSource:
        env_vars = {
            "wl_new_episode_schedule__monitor_episode_cron": "*/7 * * * *",
            "wl_new_episode_schedule__cleanup_episodes_stuck_without_media_cron": "*/40 * * * *",
        }

        def __call__(self):
            return {}

    data = environment_settings_source_data(FakeSource(), AppSettings)

    assert "newEpisodeSchedule" not in data


def test_legacy_episode_monitor_yaml_names_are_not_normalized_to_new_fields():
    from config.settings.base import normalize_settings_source_keys
    from config.settings.settings import AppSettings

    data = normalize_settings_source_keys(
        {
            "newEpisodeSchedule": {
                "monitorEpisodeCron": "*/7 * * * *",
                "cleanupEpisodesStuckWithoutMediaCron": "*/40 * * * *",
            }
        },
        AppSettings,
    )

    schedule = data["newEpisodeSchedule"]
    assert schedule == {
        "monitorEpisodeCron": "*/7 * * * *",
        "cleanupEpisodesStuckWithoutMediaCron": "*/40 * * * *",
    }
    assert "monitorPendingEpisodeCron" not in schedule
    assert "monitorNoUsableMediaEpisodeCron" not in schedule
