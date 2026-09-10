from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock


def _episode(*, title: str = "Same title") -> SimpleNamespace:
    return SimpleNamespace(
        show=SimpleNamespace(slug="test-show", title="Test Show"),
        season=None,
        slug="episode-slug",
        title=title,
        episode_identifier="ep.1",
        published_date=None,
    )


def test_unique_episode_download_path_numbers_database_reservations(tmp_path, monkeypatch):
    from backend.utils.download_paths import resolve_unique_episode_download_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    reserved = tmp_path.resolve() / "test-show" / "Same title.ext"
    session = Mock()
    session.scalars.return_value = [str(reserved)]

    path = resolve_unique_episode_download_path(
        session,
        "/downloads/{{ show }}/{{ title }}.ext",
        episode=_episode(),
    )

    assert path == tmp_path.resolve() / "test-show" / "Same title-1.ext"


def test_unique_episode_download_path_skips_existing_files(tmp_path, monkeypatch):
    from backend.utils.download_paths import resolve_unique_episode_download_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    directory = tmp_path.resolve() / "test-show"
    directory.mkdir(parents=True)
    reserved = directory / "Same title.ext"
    (directory / "Same title-1.m4a").write_bytes(b"existing")

    session = Mock()
    session.scalars.return_value = [str(reserved)]

    path = resolve_unique_episode_download_path(
        session,
        "/downloads/{{ show }}/{{ title }}.ext",
        episode=_episode(),
    )

    assert path == directory / "Same title-2.ext"


def test_unique_episode_download_path_keeps_existing_number_for_same_download(tmp_path, monkeypatch):
    from backend.utils.download_paths import resolve_unique_episode_download_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    current_path = tmp_path.resolve() / "test-show" / "Same title-1.m4a"
    current_path.parent.mkdir(parents=True)
    current_path.write_bytes(b"own artifact")

    session = Mock()
    session.scalars.return_value = []
    current_download = SimpleNamespace(id=42, file_path=str(current_path))

    path = resolve_unique_episode_download_path(
        session,
        "/downloads/{{ show }}/{{ title }}.ext",
        episode=_episode(),
        current_download=current_download,
    )

    assert path == current_path


def test_unique_episode_download_path_repairs_legacy_duplicate_on_redownload(tmp_path, monkeypatch):
    from backend.utils.download_paths import resolve_unique_episode_download_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    current_path = tmp_path.resolve() / "test-show" / "Same title.m4a"
    current_path.parent.mkdir(parents=True)
    current_path.write_bytes(b"shared old artifact")

    session = Mock()
    # Another MediaDownload still reserves the original basename. The current
    # download must move to a numbered reservation instead of overwriting it.
    session.scalars.return_value = [str(current_path)]
    current_download = SimpleNamespace(id=42, file_path=str(current_path))

    path = resolve_unique_episode_download_path(
        session,
        "/downloads/{{ show }}/{{ title }}.ext",
        episode=_episode(),
        current_download=current_download,
    )

    assert path == tmp_path.resolve() / "test-show" / "Same title-1.ext"


def test_replace_download_path_extension_preserves_numbered_basename(tmp_path):
    from backend.utils.download_paths import replace_download_path_extension

    path = tmp_path / "Same title-3.ext"
    assert replace_download_path_extension(path, "m4a") == tmp_path / "Same title-3.m4a"
