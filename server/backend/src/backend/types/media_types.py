from enum import Enum


class MediaType(Enum):
    EPISODE = "episode"
    MOVIE = "movie"

    # For instances of MediaItem class (parent class)
    MEDIA = "media"