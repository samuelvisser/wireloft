from enum import Enum


class PreferredFormat(str, Enum):
    FORMAT_4K = 'format_4k'
    FORMAT_1080P = 'format_1080p'
    FORMAT_720P = 'format_720p'
    FORMAT_AUDIO_ONLY = 'format_audio_only'
