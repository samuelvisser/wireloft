from typing import Any, Literal, TypeAlias, Union
from typing import Annotated
from pydantic import BeforeValidator

from dailywire_api.types.user_info import DwMembershipLevel

Tier: TypeAlias = Union[DwMembershipLevel, Literal["UNKNOWN"]]

def parse_tiers(v: Any) -> list[Tier]:
    if v is None:
        return []
    if isinstance(v, (str, DwMembershipLevel)):
        v = [v]
    out: list[Tier] = []
    for item in v:
        if isinstance(item, DwMembershipLevel):
            out.append(item); continue
        if not isinstance(item, str):
            continue
        key = item.strip().upper()
        try:
            out.append(DwMembershipLevel[key])  # lookup by member name
        except KeyError:
            out.append("UNKNOWN")
    return out

type AvailableForList = Annotated[list[Tier], BeforeValidator(parse_tiers)]