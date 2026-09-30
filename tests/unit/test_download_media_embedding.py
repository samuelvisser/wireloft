"""Verify actual muxed outputs, not just a successful FFmpeg command line."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from dailywire_downloader.ffmpeg import embed_media

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and ffprobe are required for media-output verification",
)


def ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30,
    )


@pytest.mark.parametrize("audio_only", [False, True], ids=["mp4", "m4a"])
@pytest.mark.parametrize("with_metadata", [False, True], ids=["artwork", "artwork-and-metadata"])
def test_embedded_artwork_survives_the_actual_muxer(tmp_path: Path, audio_only: bool, with_metadata: bool):
    media = tmp_path / ("episode.m4a" if audio_only else "episode.mp4")
    image = tmp_path / "artwork.jpg"
    if audio_only:
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.2", "-c:a", "aac", str(media))
    else:
        ffmpeg("-f", "lavfi", "-i", "color=s=64x64:r=10", "-t", "0.2", "-c:v", "mpeg4", "-threads", "1", str(media))
    ffmpeg("-f", "lavfi", "-i", "color=s=32x32", "-frames:v", "1", "-threads", "1", str(image))

    embed_media(
        str(media), thumbnail_path=str(image), audio_only=audio_only,
        metadata={"title": "Example", "show": "Example Show", "season_number": "2"} if with_metadata else None,
        should_cancel=lambda: False,
    )
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(media)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True, timeout=30,
    )
    details = json.loads(result.stdout)
    artwork = [stream for stream in details["streams"] if stream["disposition"].get("attached_pic")]
    assert len(artwork) == 1
    assert artwork[0]["codec_name"] == "mjpeg"
    assert len(details["streams"]) == 2
    if with_metadata:
        assert details["format"]["tags"]["title"] == "Example"
        assert details["format"]["tags"]["show"] == "Example Show"
        assert details["format"]["tags"]["season_number"] == "2"
    assert not Path(str(media) + ".metadata.part").exists()
