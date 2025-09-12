import enum

class ShowType(enum.Enum):
    podcast = "podcast"
    series = "series"

class EpisodeIdentifier(enum.Enum):
    date_based = "date_based"
    numbered = "numbered"