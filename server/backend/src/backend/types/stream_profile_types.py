from enum import Enum


class StreamProfileType(Enum):
    SHOW = "show"
    DOWNLOAD = "download"

    # For instances of StreamProfileBase class (parent class)
    BASE = "base"