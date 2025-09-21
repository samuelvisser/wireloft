from enum import Enum


class ShowType(Enum):
    PODCAST = "podcast"
    SERIES = "series"

class EpisodeIdentifier(Enum):
    DATE_BASED = "date_based"
    NUMBERED = "numbered"