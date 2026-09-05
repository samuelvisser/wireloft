from types import SimpleNamespace

from backend.utils.output_template import resolve_movie_output_path
from config import get_settings
from config.settings.settings import AppSettings
from config.settings.submodels import DownloadSettings, FilenameRestrictionMode


def _movie(title: str = "Amélie: Test?") -> SimpleNamespace:
    return SimpleNamespace(
        slug="movie",
        title=title,
        extended_title=None,
        duration=7200,
        dw_id="movie-1",
        author_name="François",
        mature_rating="PG",
    )


def _resolve(tmp_path, monkeypatch, mode: FilenameRestrictionMode, title: str = "Amélie: Test?") -> str:
    settings = get_settings()
    monkeypatch.setattr(settings.download_settings, "download_root", tmp_path)
    monkeypatch.setattr(settings.download_settings, "filename_restriction_mode", mode)

    path = resolve_movie_output_path(
        "/downloads/Fïlms: Collection/{{ title }}.ext",
        movie=_movie(title),
        extension="mp4",
    )
    return path.relative_to(tmp_path.resolve()).as_posix()


def test_filename_restriction_mode_defaults_to_windows():
    defaults = AppSettings.model_fields["download_settings"].default
    assert defaults.filename_restriction_mode == FilenameRestrictionMode.WINDOWS
    assert "ascii_only_filenames" not in DownloadSettings.model_fields


def test_unrestricted_mode_preserves_unicode_and_non_path_punctuation(tmp_path, monkeypatch):
    relative = _resolve(tmp_path, monkeypatch, FilenameRestrictionMode.UNRESTRICTED)
    assert relative == "Fïlms: Collection/Amélie: Test?.mp4"


def test_unrestricted_mode_does_not_allow_metadata_to_create_path_levels(tmp_path, monkeypatch):
    relative = _resolve(tmp_path, monkeypatch, FilenameRestrictionMode.UNRESTRICTED, title="Part 1/Part 2")
    assert relative == "Fïlms: Collection/Part 1_Part 2.mp4"


def test_windows_mode_preserves_unicode_but_removes_windows_invalid_characters(tmp_path, monkeypatch):
    relative = _resolve(tmp_path, monkeypatch, FilenameRestrictionMode.WINDOWS)
    assert relative == "Fïlms_ Collection/Amélie_ Test_.mp4"


def test_windows_mode_protects_reserved_device_names(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.download_settings, "download_root", tmp_path)
    monkeypatch.setattr(
        settings.download_settings,
        "filename_restriction_mode",
        FilenameRestrictionMode.WINDOWS,
    )

    path = resolve_movie_output_path(
        "/downloads/{{ title }}.ext",
        movie=_movie("CON"),
        extension="mp4",
    )
    assert path.relative_to(tmp_path.resolve()).as_posix() == "_CON.mp4"


def test_restricted_mode_uses_conservative_ascii_names(tmp_path, monkeypatch):
    relative = _resolve(tmp_path, monkeypatch, FilenameRestrictionMode.RESTRICTED)
    assert relative == "Films_Collection/Amelie_Test.mp4"
    assert relative.isascii()
