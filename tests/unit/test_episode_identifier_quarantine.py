from datetime import datetime, timezone
from types import SimpleNamespace


def _record(number: int):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{number}",
        slug=f"replacement-{number}",
        title=f"Episode {number}",
        description=None,
        duration=3600,
        episode_number=f"{number}.00",
        display_episode_number=str(number),
        background_image_path=None,
        sharing_url=f"https://example.test/{number}",
        publish_status="PUBLISHED",
        is_downloadable=True,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 9, 7, 10, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def test_reclaimed_head_advances_rolled_back_numbered_counter():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.mapper import _identify_with_vacated_reclaims

    replacement = _record(2500)
    mapped, values = _identify_with_vacated_reclaims(
        identifier_type=EpisodeIdentifier.NUMBERED,
        episodes=[replacement],
        current_values={
            "ep_id.latest_ep_num": 2499,
            "ep_id.latest_ep_extra_num": 7,
            "ep_id.latest_aux_num": 3,
        },
        season=SimpleNamespace(index=1),
        vacated_identifiers={"ep.2500"},
    )

    assert mapped == [("ep.2500", replacement)]
    assert values["ep_id.latest_ep_num"] == 2500
    assert values["ep_id.latest_ep_extra_num"] == 0
    assert values["ep_id.latest_aux_num"] == 3


def test_reclaimed_older_identifier_never_rewinds_newer_counter():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.mapper import _identify_with_vacated_reclaims

    replacement = _record(2500)
    mapped, values = _identify_with_vacated_reclaims(
        identifier_type=EpisodeIdentifier.NUMBERED,
        episodes=[replacement],
        current_values={
            "ep_id.latest_ep_num": 2501,
            "ep_id.latest_ep_extra_num": 2,
        },
        season=SimpleNamespace(index=1),
        vacated_identifiers={"ep.2500"},
    )

    assert mapped == [("ep.2500", replacement)]
    assert values["ep_id.latest_ep_num"] == 2501
    assert values["ep_id.latest_ep_extra_num"] == 2
