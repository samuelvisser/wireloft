from __future__ import annotations

from datetime import datetime


def test_show_output_template_supports_season_index(tmp_path, monkeypatch):
    from backend.db.models import Episode, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.output_template import episode_output_template_values, resolve_episode_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    show = Show(
        uuid="show-season-index",
        slug="the-ben-shapiro-show",
        title="The Ben Shapiro Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(
        show=show,
        index=12,
        slug="the-ben-shapiro-show-2026-season",
        name="2026",
    )
    episode = Episode(
        uuid="episode-season-index",
        type="episode",
        show=show,
        season=season,
        index=2497,
        episode_identifier="ep.2497",
        slug="episode-2497",
        title="Example Episode",
        description=None,
        downloaded_date=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/episode-2497",
        published_date=datetime(2026, 9, 3, 20, 0, 0),
    )

    values = episode_output_template_values(episode)
    assert values["season_name"] == "2026"
    assert values["season_index"] == "12"

    output_path = resolve_episode_output_path(
        "/downloads/Video/TV Shows/{{ show_title }}/Season {{ season_index }}/"
        "{{ show_title }} - {{ date }} - {{ title }}.ext",
        episode=episode,
        extension="mp4",
    )

    assert output_path == (
        tmp_path
        / "Video"
        / "TV Shows"
        / "The Ben Shapiro Show"
        / "Season 12"
        / "The Ben Shapiro Show - 2026-09-03 - Example Episode.mp4"
    ).resolve()
