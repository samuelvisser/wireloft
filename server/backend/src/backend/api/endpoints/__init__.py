from .dailywire import dailywire_router
from .podcast_download_profiles import download_profile_podcast_router
from .series_download_profiles import download_profile_series_router
from .download_profiles import download_profile_router
from .seasons import season_router
from .episodes import episode_router
from .media_downloads import media_download_router
from .local_media_profiles import local_media_profile_router
from .movies import movie_router
from .onboarding import onboarding_router
from .operations import operation_router
from .puller import puller_router
from .settings import setting_router
from .shows import show_router
from .config import config_router
from .tasks import task_router
from .rss_stream_profiles import rss_stream_profile_router
from .stream_profiles import stream_profile_router
from .feeds import feeds_router

from .meta_router import router as meta_router
