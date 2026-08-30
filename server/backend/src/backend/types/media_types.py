from enum import Enum


class MediaType(Enum):
    EPISODE = "episode"
    MOVIE = "movie"
    MOVIE_EXTRA = "movie_extra"

    # For instances of parent class
    BASE = "base"


class MovieExtraType(str, Enum):
    BEHIND_THE_SCENES = "behindthescenes"
    DELETED = "deleted"
    FEATURETTE = "featurette"
    INTERVIEW = "interview"
    SCENE = "scene"
    SHORT = "short"
    TRAILER = "trailer"
    OTHER = "other"
