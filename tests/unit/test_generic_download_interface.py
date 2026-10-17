"""The standalone downloader consumes explicit arguments, never WireLoft state."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from dailywire_downloader import SidecarSpec, download_media
from dailywire_downloader.models import DownloadResult


def test_full_download_from_resolved_file_and_generated_sidecar(tmp_path, monkeypatch):
    from dailywire_downloader import coordinator

    calls = []
    def transfer(url, path, *, progress, should_cancel):
        calls.append(url)
        Path(path).write_bytes(b"complete media")
        return DownloadResult(path, len(b"complete media"))
    monkeypatch.setattr(coordinator, "download_file", transfer)

    destination = tmp_path / "out" / "episode.mp4"
    execution = download_media(
        "https://cdn.example/selected.mp4", destination,
        transfer="file", format_label="selected 720p",
        download_mode="temporary", temporary_root=tmp_path / "tmp",
        sidecars=(SidecarSpec("nfo", "nfo", content=b"<episodedetails/>", extension="nfo"),),
    )
    try:
        assert calls == ["https://cdn.example/selected.mp4"]
        assert destination.read_bytes() == b"complete media"
        assert destination.with_suffix(".nfo").read_bytes() == b"<episodedetails/>"
        assert execution.format_downloaded == "selected 720p"
        assert execution.result.path == str(destination)
        assert len(execution.assets) == 1
    finally:
        execution.cleanup_workspace()


def test_flat_arguments_are_translated_into_complete_processing_plan(tmp_path, monkeypatch):
    import dailywire_downloader.api as api
    from dailywire_downloader.lifecycle import DownloadTracker

    seen = []
    monkeypatch.setattr(
        api, "execute_download_plan",
        lambda plan, **kwargs: seen.append((plan, kwargs)) or SimpleNamespace(),
    )
    tracker = DownloadTracker()
    result = download_media(
        "https://cdn.example/720.m3u8", tmp_path / "movie.mp4",
        transfer="hls", remux_to_mp4=True, extension="mp4",
        metadata_tags={"title": "Sample", "artist": "Host"},
        sidecars=(SidecarSpec("image", "thumbnail", url="https://cdn.example/cover.jpg", publish=False),),
        artwork_asset_id="image",
        download_mode="direct", tracker=tracker,
    )
    assert result is not None
    plan, values = seen[0]
    assert plan.attempt_id == tracker.attempt_id
    assert plan.source.url == "https://cdn.example/720.m3u8"
    assert plan.source.use_hls is True
    assert plan.source.remux_to_mp4 is True
    assert plan.metadata_tags == (("title", "Sample"), ("artist", "Host"))
    assert plan.stage("embed").depends_on == ("remux", "acquire:image")
    assert values["tracker"] is tracker


@pytest.mark.parametrize("url,destination,extension", [
    ("dailywire://episode", "movie.mp4", None),
    ("https://cdn.example/file", "movie", None),
    ("https://cdn.example/movie.mp4", "movie.mp4", "mkv"),
])
def test_invalid_download_arguments_fail_before_network_or_storage(url, destination, extension):
    with pytest.raises(ValueError):
        download_media(url, destination, extension=extension)


def test_cli_uses_the_same_facade_and_supplies_sidecars(tmp_path, monkeypatch, capsys):
    from dailywire_downloader import __main__ as cli

    nfo = tmp_path / "media.nfo"
    nfo.write_bytes(b"<movie/>")
    calls = []
    cleaned = []
    def fake_download(url, destination, **kwargs):
        calls.append((url, destination, kwargs))
        return SimpleNamespace(
            result=DownloadResult(destination, 12),
            assets=(),
            cleanup_workspace=lambda: cleaned.append(True),
        )
    monkeypatch.setattr(cli, "download_media", fake_download)
    exit_code = cli.main([
        "download", "https://cdn.example/master.m3u8",
        str(tmp_path / "movie.m3u8"),
        "--transfer", "hls_bundle", "--metadata", "title=An example",
        *(argument for height, url in ((480, "https://cdn.example/480.m3u8"),
                                     (720, "https://cdn.example/720.m3u8"),
                                     (1080, "https://cdn.example/1080.m3u8"))
          for argument in ("--hls-rendition", f"{height}={url}")),
        "--generated-sidecar", f"nfo={nfo}", "--quiet",
    ])
    assert exit_code == 0
    assert calls[0][2]["transfer"] == "hls_bundle"
    assert calls[0][2]["hls_renditions"] == (
        (480, "https://cdn.example/480.m3u8"),
        (720, "https://cdn.example/720.m3u8"),
        (1080, "https://cdn.example/1080.m3u8"),
    )
    assert calls[0][2]["metadata_tags"] == {"title": "An example"}
    assert calls[0][2]["sidecars"][0].content == b"<movie/>"
    assert cleaned == [True]
    assert "saved 12 transferred bytes" in capsys.readouterr().out


def test_downloader_does_not_import_domain_provider_or_database_packages():
    import dailywire_downloader
    root = Path(dailywire_downloader.__file__).parent
    forbidden = {"backend", "task_manager", "sqlalchemy", "dailywire_api", "dailywire_authorisation", "config"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.split(".")[0] in forbidden for name in names), path


def test_hls_bundle_requires_preselected_sources(tmp_path):
    with pytest.raises(ValueError, match="preselected rendition URLs"):
        download_media(
            "https://cdn.example/master.m3u8", tmp_path / "output.m3u8",
            transfer="hls_bundle",
        )


def test_non_bundle_download_refuses_unused_rendition_arguments(tmp_path):
    with pytest.raises(ValueError, match="only apply to bundle"):
        download_media(
            "https://cdn.example/media.mp4", tmp_path / "movie.mp4",
            transfer="file", hls_renditions=((720, "https://cdn.example/720.m3u8"),),
        )


def test_hls_bundle_passes_exact_renditions_to_execution(tmp_path, monkeypatch):
    import dailywire_downloader.api as api
    from dailywire_downloader.lifecycle import DownloadTracker

    plans = []
    monkeypatch.setattr(
        api, "execute_download_plan",
        lambda plan, **_kwargs: plans.append(plan) or SimpleNamespace(),
    )
    renditions = (
        (360, "https://cdn.example/360.m3u8"),
        (720, "https://cdn.example/720.m3u8"),
    )
    download_media(
        "https://cdn.example/master.m3u8", tmp_path / "movie.m3u8",
        transfer="hls_bundle", hls_renditions=renditions,
        tracker=DownloadTracker(),
    )
    assert plans[0].source.hls_renditions == renditions


@pytest.mark.parametrize("renditions", [
    ((0, "https://cdn.example/0.m3u8"),),
    ((720, "https://cdn.example/720.m3u8"), (720, "https://cdn.example/720-alt.m3u8")),
    ((360, "https://cdn.example/same.m3u8"), (720, "https://cdn.example/same.m3u8")),
    ((720, "local.m3u8"),),
])
def test_invalid_hls_renditions_fail_before_network(tmp_path, renditions):
    with pytest.raises(ValueError, match="rendition heights and HTTP"):
        download_media(
            "https://cdn.example/master.m3u8", tmp_path / "movie.m3u8",
            transfer="hls_bundle", hls_renditions=renditions,
        )
