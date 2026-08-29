from enum import Enum


class MediaType(Enum):
    EPISODE = "episode"
    MOVIE = "movie"
    TRAILER = "trailer"

    # For instances of parent class
    BASE = "base"
