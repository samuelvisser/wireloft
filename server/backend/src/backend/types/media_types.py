from enum import Enum


class MediaType(Enum):
    episode = "episode"
    movie = "movie"

    # For instances of MediaItem class (parent class)
    media = "media"