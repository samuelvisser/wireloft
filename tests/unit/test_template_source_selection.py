from backend.api.endpoints.local_media_profiles.template_source_selection import _balanced_episode_ids


def test_balanced_episode_ids_evenly_spreads_ten_slots_over_four_shows():
    show_ids = [1, 2, 3, 4]
    episodes = {
        1: [11, 12, 13],
        2: [21, 22, 23],
        3: [31, 32, 33],
        4: [41, 42, 43],
    }

    selected = _balanced_episode_ids(show_ids, episodes, 10)

    assert selected == [11, 21, 31, 41, 12, 22, 32, 42, 13, 23]


def test_balanced_episode_ids_uses_one_episode_per_show_when_ten_are_available():
    show_ids = list(range(1, 11))
    episodes = {show_id: [show_id * 10 + 1, show_id * 10 + 2] for show_id in show_ids}

    selected = _balanced_episode_ids(show_ids, episodes, 10)

    assert selected == [show_id * 10 + 1 for show_id in show_ids]


def test_balanced_episode_ids_skips_exhausted_shows_and_keeps_filling():
    show_ids = [1, 2, 3]
    episodes = {
        1: [11],
        2: [21, 22, 23],
        3: [31, 32, 33],
    }

    selected = _balanced_episode_ids(show_ids, episodes, 6)

    assert selected == [11, 21, 31, 22, 32, 23]
