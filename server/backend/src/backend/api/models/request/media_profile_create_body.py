from pydantic import ConfigDict, AliasGenerator
from pydantic.alias_generators import to_camel

from backend.api.models.response import MediaProfileItemResponse


class MediaProfileCreateBody(MediaProfileItemResponse):

    def __init__(self):
        super().__init__()

        self.model_config.setdefault('alias_generator', AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=to_camel,
        ))

    name: str
    outputPathTemplate: str
    preferredFormat: str | None = None
    downloadSeriesImages: bool