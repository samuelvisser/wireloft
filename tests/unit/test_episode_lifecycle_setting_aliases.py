def test_legacy_episode_monitor_environment_names_fill_new_fields():
    from config.settings.settings import AppSettings, environment_settings_source_data

    class FakeSource:
        env_vars = {
            "wl_new_episode_schedule__monitor_episode_cron": "*/7 * * * *",
            "wl_new_episode_schedule__cleanup_episodes_stuck_without_media_cron": "*/40 * * * *",
        }

        def __call__(self):
            return {}

    data = environment_settings_source_data(FakeSource(), AppSettings)

    assert data["newEpisodeSchedule"]["monitor_pending_episode_cron"] == "*/7 * * * *"
    assert data["newEpisodeSchedule"]["monitor_no_usable_media_episode_cron"] == "*/40 * * * *"


def test_canonical_episode_monitor_environment_names_win_over_legacy_aliases():
    from config.settings.settings import AppSettings, environment_settings_source_data

    class FakeSource:
        env_vars = {
            "wl_new_episode_schedule__monitor_episode_cron": "*/7 * * * *",
            "wl_new_episode_schedule__cleanup_episodes_stuck_without_media_cron": "*/40 * * * *",
        }

        def __call__(self):
            return {
                "newEpisodeSchedule": {
                    "monitorPendingEpisodeCron": "*/2 * * * *",
                    "monitorNoUsableMediaEpisodeCron": "*/20 * * * *",
                }
            }

    data = environment_settings_source_data(FakeSource(), AppSettings)

    assert data["newEpisodeSchedule"]["monitorPendingEpisodeCron"] == "*/2 * * * *"
    assert data["newEpisodeSchedule"]["monitorNoUsableMediaEpisodeCron"] == "*/20 * * * *"
    assert "monitor_pending_episode_cron" not in data["newEpisodeSchedule"]
    assert "monitor_no_usable_media_episode_cron" not in data["newEpisodeSchedule"]
