from typing import Optional

from dailywire_api.records.DwEpisodeRecord import DwEpisodeRecord


class DwEpisodeDetailRecord(DwEpisodeRecord):

    segment_audio_url: Optional[str]
    audio_url: str
    video_url: str
    secure_video_url: str
    progress: float
    delivery_mode: str
    continue_watching_entity_type: Optional[str]
    continue_watching_entity_id: Optional[str]
    playback_policy: Optional[str]
    mux_playback_id: Optional[str]
    mux_playback_token: Optional[str]
    mux_drm_token: Optional[str]
    next_episode_url: Optional[str]