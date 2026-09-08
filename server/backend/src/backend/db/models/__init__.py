# Ensure base and referenced tables are imported before dependents
from .local_media_profile import (
    LocalMediaProfileBase,
    MovieLocalMediaProfile,
    ShowLocalMediaProfile,
)

# Existing code and third-party integrations historically constructed
# ``LocalMediaProfile`` directly for shows. Keep that import compatible while
# production code that needs all types queries ``LocalMediaProfileBase``.
LocalMediaProfile = ShowLocalMediaProfile
from .Season import Season
from .Settings import Settings
from .Show import Show
from .Metadata import Metadata

from .download_profile import DownloadProfileBase
from .media_download import MediaDownloadBase
from .media_item import MediaItemBase
from .stream_profile import StreamProfileBase

from .download_profile import PodcastDownloadProfile
from .download_profile import SeriesDownloadProfile
from .media_download import EpisodeMediaDownload
from .media_download import MovieMediaDownload
from .media_download import MovieExtraMediaDownload
from .media_item import Episode
from .media_item import Movie
from .media_item import MovieExtra
from .stream_profile import RssStreamProfile
