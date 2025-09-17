from enum import Enum


class ShowType(Enum):
    podcast = "podcast"
    series = "series"

class EpisodeIdentifier(Enum):
    date_based = "date_based"
    numbered = "numbered"