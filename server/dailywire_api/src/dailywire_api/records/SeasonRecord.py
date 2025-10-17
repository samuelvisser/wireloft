from pydantic import Field

from dailywire_api.records.BaseRecord import BaseRecord

class SeasonRecord(BaseRecord):
    dw_id: str = Field(validation_alias="id")
    name: str
    slug: str