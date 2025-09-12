import enum

class MediaType(enum.Enum):
    episode = "episode"
    movie = "movie"

    # For instances of MediaItem class (parent class)
    media = "media"