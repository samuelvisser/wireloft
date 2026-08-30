from types import SimpleNamespace

from backend.utils.output_template import resolve_episode_output_path, resolve_movie_output_path
from config import get_settings
from config.settings.settings import AppSettings


def test_ascii_only_filenames_defaults_to_true():
    defaults = AppSettings.model_fields["download_settings"].default
    assert defaults.ascii_only_filenames is True


def test_episode_output_path_is_ascii_only_when_enabled(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.download_settings, "download_root", tmp_path)
    monkeypatch.setattr(settings.download_settings, "ascii_only_filenames", True)

    episode = SimpleNamespace(
        episode_identifier="ep.1",
        slug="cafe-episode",
        title="Café déjà vu 🎬",
        published_date=None,
        show=SimpleNamespace(slug="show", title="Shöw"),
        season=SimpleNamespace(slug="season", name="Séasön"),
    )

    path = resolve_episode_output_path(
        "/downloads/Mövíes/{show_title}/{season_name}/{title}.ext",
        episode=episode,
        extension="mp4",
    )

    relative = path.relative_to(tmp_path.resolve()).as_posix()
    assert relative == "Movies/Show/Season/Cafe deja vu.mp4"
    assert relative.isascii()


def test_movie_output_path_is_ascii_only_when_enabled(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.download_settings, "download_root", tmp_path)
    monkeypatch.setattr(settings.download_settings, "ascii_only_filenames", True)

    movie = SimpleNamespace(
        slug="movie",
        title="Amélie 🎥",
        extended_title=None,
        duration=7200,
        dw_id="movie-1",
        author_name="François",
        mature_rating="PG",
    )

    path = resolve_movie_output_path(
        "/downloads/Fïlms/{title}.ext",
        movie=movie,
        extension="mp4",
    )

    relative = path.relative_to(tmp_path.resolve()).as_posix()
    assert relative == "Films/Amelie.mp4"
    assert relative.isascii()


def test_unicode_is_preserved_when_ascii_only_filenames_is_disabled(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.download_settings, "download_root", tmp_path)
    monkeypatch.setattr(settings.download_settings, "ascii_only_filenames", False)

    movie = SimpleNamespace(
        slug="movie",
        title="Amélie",
        extended_title=None,
        duration=7200,
        dw_id="movie-1",
        author_name="François",
        mature_rating="PG",
    )

    path = resolve_movie_output_path(
        "/downloads/Fïlms/{title}.ext",
        movie=movie,
        extension="mp4",
    )

    relative = path.relative_to(tmp_path.resolve()).as_posix()
    assert relative == "Fïlms/Amélie.mp4"
    assert not relative.isascii()
