from __future__ import annotations

from wireloft_controller.m3u8 import get_vod_info
from wireloft_controller.m3u8.get_vod_info import _fmt_hhmmss
from wireloft_scheduler.registry import task


@task(
    key="download_series_thumbnail",
    title="Download series thumbnail",
    description="Downloads a series thumbnail image to the media profile output directory for the given download profile.",
    allowed_resource_types=("download_profile_series",),
    default_max_retries=5,
    tracks_progress=False,
)
async def download_series_thumbnail(*, resource_id: int, progress):  # progress provided by executor
    """Given a DownloadProfileSeries id, download the show's thumbnail into the media output dir.

    The saved file will be named 'series_thumbnail.jpg' in the target directory.
    """

    info = get_vod_info("https://stream.media.dailywire.com/sYA9ENZjdsGW8GqQuKsxXLVbIJ7V9nRy.m3u8?token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ2IiwiZXhwIjoxNzYyNjI1NzA4LCJraWQiOiJCZXVLOE1NaE9SVzAxTEpYMXhZV2tJQmE3NmxQMVlNZzAwIiwic3ViIjoic1lBOUVOWmpkc0dXOEdxUXVLc3hYTFZiSUo3VjluUnkifQ.r_iJxOz18h4qbjXB5PYk8lEu-SHVqPq44yNBsXhU75TStvusR3xYtJd-GiMhTZLCP44qTn5aKMuJEaK-RXVomDWwuum41edqH_ATkAvuGVJgPHcZtB19DOjvRMqAwwsBqCm_u9ZI1ENLn61x6cv7LKPWLhjihjejtvF7jsn2_vN0yvtHEIAaNCHhM43PCvE3ucelRpdSggNPKLtcyHBPkD9hT0yg8lJpPnZ8oDVCsVFFsohNcZ3wjvK9t64RumdFjkXtUQ1dbbk_7tTEeSTupyojNx7xHuSoldtmtoOVbbmPhWAzWI8nlmfg6Ty7-rmMvJCg4R0IGcTNigA0YN-6bw")

    print(f"type={info.playlist_type}")
    print(f"seconds={info.seconds}")
    print(f"hhmmss={_fmt_hhmmss(info.seconds)}")
    print(f"segments={info.segments}")
    print(f"variant_url={info.variant_url}")

    # with db_session():
    #     await run_download_series_thumbnail(resource_id=resource_id, progress=progress)