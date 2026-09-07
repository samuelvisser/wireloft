import pytest


def test_episode_no_show_today_is_getter_only_and_derived_from_slug():
    from backend.db.models import Episode

    episode = Episode(slug="show-123-no-show-today")
    assert episode.is_no_show_today is True

    episode.slug = "show-123"
    assert episode.is_no_show_today is False

    with pytest.raises(AttributeError):
        episode.is_no_show_today = True

    assert isinstance(Episode.__dict__["is_no_show_today"], property)
