from backend.db.models import Episode, PodcastDownloadProfile, SeriesDownloadProfile
from sqlalchemy.orm import Session


def get_download_profile_episodes(s: Session, profile: PodcastDownloadProfile | SeriesDownloadProfile) -> list[Episode]:
    ...