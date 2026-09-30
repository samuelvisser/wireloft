from __future__ import annotations

from dataclasses import replace

import pytest

from dailywire_downloader.lifecycle import DownloadTracker
from dailywire_downloader.plan import ResolvedDownloadSource, SidecarSpec, build_download_plan


def make_plan(tmp_path, *, tracker=None, remux=False, **options):
    return build_download_plan(
        source=ResolvedDownloadSource(
            "https://media.test/stream", "1080p", remux, remux, "mp4", False,
        ),
        requested_destination=tmp_path / "library" / "Movie.mp4",
        download_mode="temporary", temporary_root=tmp_path / "temporary",
        attempt_id=tracker.attempt_id if tracker is not None else None,
        **options,
    )


def test_plan_records_dependencies_for_parallel_assets_and_serial_media_mutations(tmp_path):
    value = make_plan(
        tmp_path, remux=True,
        assets=(SidecarSpec("artwork", "thumbnail", url="https://media.test/art.jpg"),
                SidecarSpec("nfo", "nfo", content=b"<movie/>", extension="nfo")),
        artwork_asset_id="artwork", metadata_tags=(("title", "Movie"),),
    )
    assert value.stage("media").depends_on == ("prepare",)
    assert value.stage("acquire:artwork").depends_on == ("prepare",)
    assert value.stage("acquire:nfo").depends_on == ("prepare",)
    assert value.stage("remux").depends_on == ("media",)
    assert value.stage("embed").depends_on == ("remux", "acquire:artwork")
    assert value.stage("publish").depends_on == ("embed", "acquire:artwork", "acquire:nfo")
    assert value.stage("publish:nfo").depends_on == ("publish", "acquire:nfo")
    assert value.stage("verify").depends_on == ("publish", "publish:artwork", "publish:nfo")
    assert value.stage("finalize").depends_on == ("verify",)
    assert value.stage("remux").deadline_seconds == 3600
    assert value.stage("embed").deadline_seconds == 3600
    assert value.stage("publish:nfo").deadline_seconds == 1800
    assert value.stage("finalize").deadline_seconds == 120


def test_optional_stages_are_not_dependencies_when_not_requested(tmp_path):
    value = make_plan(tmp_path)
    assert [stage.id for stage in value.stages] == ["prepare", "media", "publish", "verify", "finalize"]
    assert value.stage("publish").depends_on == ("media",)
    assert value.stage("verify").depends_on == ("publish",)
    assert value.stage("media").deadline_seconds is None


def test_tracker_rejects_work_before_its_dependency_completes(tmp_path):
    tracker = DownloadTracker()
    value = make_plan(tmp_path, tracker=tracker, metadata_tags=(("title", "Movie"),))
    tracker.install(value)
    with pytest.raises(ValueError, match="unfinished dependencies: media"):
        tracker.start("embed")
    tracker.start("media")
    tracker.complete("media")
    tracker.start("embed")
    with pytest.raises(ValueError, match="unfinished dependencies: embed"):
        tracker.start("publish")
    with pytest.raises(ValueError, match="already started"):
        tracker.start("embed")


def test_skipped_optional_asset_satisfies_dependency_without_claiming_a_file(tmp_path):
    tracker = DownloadTracker()
    value = make_plan(tmp_path, tracker=tracker, assets=(
        SidecarSpec("subtitle", "subtitle", url="https://media.test/a.srt", required=False),
    ))
    tracker.install(value)
    tracker.start("media")
    tracker.complete("media")
    tracker.skip("acquire:subtitle", "Optional subtitles unavailable")
    tracker.start("publish")
    tracker.complete("publish")
    tracker.skip("publish:subtitle", "Optional subtitles were not published")
    tracker.start("verify")
    assert tracker.snapshot().main_activity == "verify"


def test_tracker_uses_deadline_in_plan_instead_of_coordinator_constant(tmp_path, monkeypatch):
    import dailywire_downloader.lifecycle as lifecycle
    tracker = DownloadTracker()
    value = make_plan(tmp_path, tracker=tracker)
    value = replace(value, stages=tuple(
        replace(stage, deadline_seconds=17) if stage.id == "publish" else stage
        for stage in value.stages
    ))
    tracker.install(value)
    tracker.start("media")
    tracker.complete("media")
    monkeypatch.setattr(lifecycle, "time", lambda: 100)
    tracker.start("publish")
    snapshot = next(stage for stage in tracker.snapshot().stages if stage.id == "publish")
    assert snapshot.deadline_at == 117
    tracker.wait("publish", "processing_capacity")
    monkeypatch.setattr(lifecycle, "time", lambda: 110)
    tracker.wait("publish", None)
    snapshot = next(stage for stage in tracker.snapshot().stages if stage.id == "publish")
    assert snapshot.deadline_at == 127


def test_plan_cannot_be_replaced_after_execution_begins(tmp_path):
    tracker = DownloadTracker()
    value = make_plan(tmp_path, tracker=tracker)
    tracker.install(value)
    with pytest.raises(ValueError, match="only install one"):
        tracker.install(value)


@pytest.mark.parametrize("dependency", ["unknown", "finalize"])
def test_plan_rejects_unknown_dependencies_and_cycles(tmp_path, dependency):
    value = make_plan(tmp_path)
    with pytest.raises(ValueError, match="dependency|cycle"):
        replace(value, stages=tuple(
            replace(stage, depends_on=(dependency,)) if stage.id == "media" else stage
            for stage in value.stages
        ))


@pytest.mark.parametrize("weight", [-1, float("nan"), float("inf")])
def test_plan_rejects_invalid_work_weights(tmp_path, weight):
    with pytest.raises(ValueError, match="work weights"):
        replace(make_plan(tmp_path).stage("media"), weight=weight)


@pytest.mark.parametrize("deadline", [0, -1, float("nan"), float("inf")])
def test_plan_rejects_invalid_deadlines(tmp_path, deadline):
    with pytest.raises(ValueError, match="deadlines"):
        replace(make_plan(tmp_path).stage("publish"), deadline_seconds=deadline)
