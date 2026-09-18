from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def _record(
    episode_number: str,
    *,
    slug: str | None = None,
    title: str = "Episode",
    is_trailer: bool | None = None,
):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug or episode_number}",
        slug=slug or f"episode-{episode_number.replace('.', '-')}",
        title=title,
        description=None,
        duration=3600,
        episode_number=episode_number,
        display_episode_number="",
        background_image_path=None,
        sharing_url="https://example.test/episode",
        publish_status="PUBLISHED",
        is_downloadable=True,
        is_trailer=is_trailer,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def _season(*, season_number: int = 1, season_type: str = "normal"):
    return SimpleNamespace(
        index=season_number,
        season_number=season_number,
        season_type=season_type,
        slug=f"season-{season_number}",
        name=f"Season {season_number}",
    )


def test_episode_identifier_info_parses_all_canonical_semantics():
    from backend.utils.episode import EpisodeIdentifierInfo

    main = EpisodeIdentifierInfo.from_identifier("ep.S02E27")
    assert main.type == "ep"
    assert main.season_number == 2
    assert main.episode_number == "27"
    assert main.sub_episode_number is None
    assert main.label == "S02E27"
    assert main.source_slot == "S02E27.0"

    extra = EpisodeIdentifierInfo.from_identifier("ep-extra.trailer.S02E27.5")
    assert extra.type == "ep-extra"
    assert extra.extra_type == "trailer"
    assert extra.season_number == 2
    assert extra.episode_number == "27"
    assert extra.sub_episode_number == "5"
    assert extra.label == "S02E27.5"
    assert extra.source_slot == "S02E27.5"

    auxiliary = EpisodeIdentifierInfo.from_identifier("aux.12")
    assert auxiliary.type == "aux"
    assert auxiliary.episode_number == "12"
    assert auxiliary.source_slot is None


def test_extra_before_main_does_not_reserve_main_number():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    extra = _record("1645.01", slug="extra-first")
    main = _record("1645.00", slug="main-later")

    mapped, values = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [extra, main],
        season=_season(),
    )

    assert [identifier for identifier, _ in mapped] == [
        "ep-extra.other.1645.1",
        "ep.1645",
    ]
    assert "ep_id.latest_ep_num" not in values
    assert "ep_id.latest_ep_extra_num" not in values


def test_extra_can_arrive_after_a_newer_main():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    late_extra = _record("1843.01")
    occupied = {"ep.1843", "ep.1844"}

    mapped, _ = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [late_extra],
        season=_season(),
        occupied_identifiers=occupied,
    )

    assert mapped[0][0] == "ep-extra.other.1843.1"


def test_all_nonzero_dailywire_segments_are_used_directly():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    mapped, values = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [_record("2000.20"), _record("2000.30", slug="second")],
        season=_season(),
    )

    assert [identifier for identifier, _ in mapped] == [
        "ep-extra.other.2000.20",
        "ep-extra.other.2000.30",
    ]
    assert "ep_id.latest_aux_num" not in values


def test_extras_season_numbers_do_not_create_episode_relationships():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    mapped, _ = identify_episodes_in_season(
        EpisodeIdentifier.SEASONAL,
        [
            _record("27.00", slug="standalone-main-shaped"),
            _record("27.10", slug="standalone-extra-shaped"),
        ],
        season=_season(season_number=0, season_type="extra"),
    )

    assert [identifier for identifier, _ in mapped] == ["aux.1", "aux.2"]


def test_attached_trailer_remains_episode_extra_with_trailer_subtype():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    mapped, _ = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [_record("2083.05", is_trailer=True)],
        season=_season(),
    )

    assert mapped[0][0] == "ep-extra.trailer.2083.5"


def test_standalone_trailer_uses_show_global_trailer_counter():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    mapped, values = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [_record("2083.00", is_trailer=True)],
        season=_season(),
    )

    assert mapped[0][0] == "trailer.1"
    assert values["ep_id.latest_trailer_num"] == 1


def test_duplicate_source_slot_ignores_episode_extra_subtype():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    first = _record("2083.05", slug="first", is_trailer=False)
    duplicate = _record("2083.05", slug="duplicate", is_trailer=True)

    mapped, _ = identify_episodes_in_season(
        EpisodeIdentifier.NUMBERED,
        [first, duplicate],
        season=_season(),
    )

    assert [identifier for identifier, _ in mapped] == [
        "ep-extra.other.2083.5",
        "aux.1",
    ]


def test_same_episode_number_is_distinct_across_seasons():
    from backend.types.show_types import EpisodeIdentifier
    from task_manager.tasks.helpers.episodes.identifier import identify_episodes_in_season

    occupied: set[str] = set()
    first, _ = identify_episodes_in_season(
        EpisodeIdentifier.SEASONAL,
        [_record("27.00", slug="season-1-episode")],
        season=_season(season_number=1),
        occupied_identifiers=occupied,
    )
    second, _ = identify_episodes_in_season(
        EpisodeIdentifier.SEASONAL,
        [_record("27.00", slug="season-2-episode")],
        season=_season(season_number=2),
        occupied_identifiers=occupied,
    )

    assert first[0][0] == "ep.S01E27"
    assert second[0][0] == "ep.S02E27"


def test_mapper_uses_detail_trailer_flag_over_title_heuristic():
    from dailywire_api.dw_api.client import EpisodesPaginatedResult
    from task_manager.tasks.helpers.episodes.mapper import get_dw_episodes_by_seasons
    from task_manager.tasks.types.general import RecordOrder

    record = _record(
        "2083.05",
        slug="reacting-to-a-movie-trailer",
        title="Reacting To A Movie Trailer",
        is_trailer=None,
    )
    authoritative = record.model_copy(update={"is_trailer": False})

    class FakeClient:
        def get_episodes_paginated(self, show_slug, selector):
            return EpisodesPaginatedResult([record], None, False)

        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == record.slug
            assert require_member_exclusive is False
            return authoritative

    season = _season()
    season.id = 11
    show = SimpleNamespace(slug="test-show", episode_identifier="numbered")

    episode_map, _ = get_dw_episodes_by_seasons(
        FakeClient(),
        show=show,
        membership_plan="FREE",
        seasons=[season],
        dw_id_by_slug={season.slug: "remote-season"},
        order=RecordOrder.ASC,
    )

    assert episode_map[season.id][0][0] == "ep-extra.other.2083.5"


def test_mapper_promotes_attached_trailer_from_authoritative_detail():
    from dailywire_api.dw_api.client import EpisodesPaginatedResult
    from task_manager.tasks.helpers.episodes.mapper import get_dw_episodes_by_seasons
    from task_manager.tasks.types.general import RecordOrder

    record = _record(
        "2083.05",
        slug="official-trailer-for-episode",
        title="Official Trailer For Episode 2083",
        is_trailer=None,
    )
    authoritative = record.model_copy(update={"is_trailer": True})

    class FakeClient:
        def get_episodes_paginated(self, show_slug, selector):
            return EpisodesPaginatedResult([record], None, False)

        def get_episode_details(self, slug, *, require_member_exclusive):
            return authoritative

    season = _season()
    season.id = 11
    show = SimpleNamespace(slug="test-show", episode_identifier="numbered")

    episode_map, _ = get_dw_episodes_by_seasons(
        FakeClient(),
        show=show,
        membership_plan="FREE",
        seasons=[season],
        dw_id_by_slug={season.slug: "remote-season"},
        order=RecordOrder.ASC,
    )

    assert episode_map[season.id][0][0] == "ep-extra.trailer.2083.5"


def test_reindex_migration_uses_the_same_canonical_identifier_rules():
    from backend.db.alembic.versions.e4c91a7b2d30_episode_indexing_semantics import (
        _direct_identifier,
        _generated_type,
    )

    other = _record("1645.01", slug="migration-extra")
    assert _direct_identifier(
        "numbered",
        season_type="normal",
        season_number=1,
        record=other,
    ) == ("ep-extra.other.1645.1", "1645.1")
    assert _generated_type(
        "numbered",
        season_type="normal",
        record=other,
    ) is None

    attached_trailer = _record(
        "2083.05",
        slug="migration-trailer",
        is_trailer=True,
    )
    assert _direct_identifier(
        "seasonal",
        season_type="normal",
        season_number=2,
        record=attached_trailer,
    ) == ("ep-extra.trailer.S02E2083.5", "S02E2083.5")

    high_segment = _record("1645.20", slug="high-segment")
    assert _direct_identifier(
        "numbered",
        season_type="normal",
        season_number=1,
        record=high_segment,
    ) == ("ep-extra.other.1645.20", "1645.20")
    assert _generated_type(
        "numbered",
        season_type="normal",
        record=high_segment,
    ) is None

    extras_item = _record("27.10", slug="extras-item")
    assert _direct_identifier(
        "seasonal",
        season_type="extra",
        season_number=0,
        record=extras_item,
    ) == (None, None)
    assert _generated_type(
        "seasonal",
        season_type="extra",
        record=extras_item,
    ) == "aux"


def test_resolved_batch_is_reidentified_from_authoritative_detail_numbers():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.save import ResolvedEpisode
    from task_manager.tasks.workers.fetch_new_episodes.service import (
        _canonicalize_resolved_identifiers,
    )

    season = _season()
    season.id = 11
    show = SimpleNamespace(
        episode_identifier="numbered",
        seasons=[season],
    )
    paginated_extra = _record("1843.01", slug="late-extra")
    paginated_main = _record("1844.00", slug="next-main")
    resolved = {
        season.id: [
            ResolvedEpisode(
                episode_identifier="ep-extra.other.1843.1",
                record=paginated_extra.model_copy(update={"episode_number": "1843.10"}),
                status=EpisodePublishStatus.PUBLISHED_FINAL,
                detail_resolved=True,
            ),
            ResolvedEpisode(
                episode_identifier="ep.1844",
                record=paginated_main,
                status=EpisodePublishStatus.PUBLISHED_FINAL,
                detail_resolved=True,
            ),
        ]
    }

    canonical, values = _canonicalize_resolved_identifiers(
        show=show,
        resolved_by_season=resolved,
        previous_values={},
        occupied_identifiers={"ep.1843"},
    )

    assert [
        episode.episode_identifier
        for episode in canonical[season.id]
    ] == [
        "ep-extra.other.1843.10",
        "ep.1844",
    ]
    assert "ep_id.latest_ep_extra_num" not in values


def test_reindex_migration_downgrade_restores_previous_identifier_grammar():
    from backend.db.alembic.versions.e4c91a7b2d30_episode_indexing_semantics import (
        _identifier_for_previous_release,
    )

    assert _identifier_for_previous_release(
        "numbered",
        season_index=4,
        identifier="ep-extra.other.1843.10",
    ) == "ep-extra.1843.10"
    assert _identifier_for_previous_release(
        "numbered",
        season_index=4,
        identifier="ep-extra.trailer.1843.5",
    ) == "ep-extra.1843.5"
    assert _identifier_for_previous_release(
        "seasonal",
        season_index=9,
        identifier="ep.S06E570",
    ) == "ep.S09E570"
    assert _identifier_for_previous_release(
        "seasonal",
        season_index=9,
        identifier="ep-extra.other.S06E570.10",
    ) == "ep-extra.S09E570.10"


def test_mapper_does_not_mutate_callers_occupied_identifier_snapshot():
    from dailywire_api.dw_api.client import EpisodesPaginatedResult
    from task_manager.tasks.helpers.episodes.mapper import get_dw_episodes_by_seasons
    from task_manager.tasks.types.general import RecordOrder

    record = _record("2500.00", slug="new-episode")

    class FakeClient:
        def get_episodes_paginated(self, show_slug, selector):
            return EpisodesPaginatedResult([record], None, False)

    season = _season()
    season.id = 11
    show = SimpleNamespace(slug="test-show", episode_identifier="numbered")
    occupied = {"ep.2499"}

    episode_map, _ = get_dw_episodes_by_seasons(
        FakeClient(),
        show=show,
        membership_plan="FREE",
        seasons=[season],
        dw_id_by_slug={season.slug: "remote-season"},
        order=RecordOrder.ASC,
        occupied_identifiers=occupied,
    )

    assert episode_map[season.id][0][0] == "ep.2500"
    assert occupied == {"ep.2499"}



def test_compact_episode_view_includes_identifier_semantics():
    import backend.db.models  # noqa: F401
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.api.endpoints.episodes.service import get_episode_views_by_show_list
    from backend.db import Base
    from backend.db.models import Episode, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

    show = Show(
        uuid="show-view-semantics",
        slug="view-semantics",
        title="View Semantics",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.SERIES.value,
        episode_identifier=EpisodeIdentifier.SEASONAL.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(
        show=show,
        index=3,
        slug="season-3",
        name="Season 3",
        season_type="normal",
        season_number=3,
    )
    episode = Episode(
        uuid="episode-view-semantics",
        type="episode",
        show=show,
        season=season,
        index=12,
        episode_identifier="ep-extra.trailer.S03E12.5",
        dw_episode_number="12.05",
        slug="season-3-episode-12-trailer",
        title="Episode 12 Trailer",
        description=None,
        downloaded_date=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode",
        published_date=datetime(2026, 9, 18, 12, 0, 0),
    )
    session.add_all([show, season, episode])
    session.commit()

    [view] = get_episode_views_by_show_list(session, show.slug)

    assert view.dw_episode_number == "12.05"
    assert view.episode_type == "ep-extra"
    assert view.episode_extra_type == "trailer"
    assert view.episode_number == "12"
    assert view.episode_sub_number == "5"
    assert view.episode_label == "S03E12.5"

    session.close()
    engine.dispose()
